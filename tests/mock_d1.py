"""
Mock D1 Database for Unit Testing

Provides a simple in-memory database implementation that mimics
D1's API for testing ORM functionality without requiring actual
Cloudflare Workers environment.
"""

import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


class MockD1Result:
    """Mock D1 query result"""
    
    def __init__(self, data: Optional[Dict] = None, results: Optional[List[Dict]] = None):
        self._data = data
        self.results = results or []
        self.meta = MagicMock()
        self.changes = 0
        
        # Set last_row_id if this is an insert
        if data is None and results:
            self.meta.last_row_id = max([r.get('id', 0) for r in results], default=0) + 1
    
    def __getitem__(self, key):
        if self._data:
            return self._data.get(key)
        return None
        
    def __contains__(self, key):
        return self._data and key in self._data
        
    def keys(self):
        return self._data.keys() if self._data else []
        
    def to_py(self):
        """Mimic D1's to_py() method"""
        return self._data if self._data else {}


class MockD1PreparedStatement:
    """Mock D1 prepared statement"""
    
    def __init__(self, db: 'MockD1Database', sql: str):
        self.db = db
        self.sql = sql
        self.params = []
        
    def bind(self, *params):
        """Bind parameters to the statement"""
        self.params = list(params)
        return self
        
    async def first(self) -> Optional[MockD1Result]:
        """Execute and return first result"""
        results = await self._execute()
        if results:
            return MockD1Result(data=results[0])
        return None
        
    async def all(self) -> MockD1Result:
        """Execute and return all results"""
        results = await self._execute()
        return MockD1Result(results=results)
        
    async def run(self) -> MockD1Result:
        """Execute statement for INSERT/UPDATE/DELETE"""
        if self.sql.strip().upper().startswith('INSERT'):
            results = await self._execute()
            result = MockD1Result()
            if results and 'id' in results[0]:
                result.meta.last_row_id = results[0]['id']
            return result
        elif self.sql.strip().upper().startswith(('UPDATE', 'DELETE')):
            await self._execute()
            result = MockD1Result()
            result.changes = 1  # Mock changes count
            return result
        else:
            await self._execute()
            return MockD1Result()
    
    async def _execute(self) -> List[Dict]:
        """Execute the SQL statement"""
        return await self.db._execute_sql(self.sql, self.params)


class MockD1Database:
    """
    Mock D1 database using SQLite in-memory
    
    Provides the same async API as D1 but uses SQLite for actual storage,
    allowing unit tests to run without Cloudflare Workers environment.
    """
    
    def __init__(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row  # Enable column access by name
        
    def prepare(self, sql: str) -> MockD1PreparedStatement:
        """Prepare an SQL statement"""
        return MockD1PreparedStatement(self, sql)
        
    async def exec(self, sql: str) -> None:
        """Execute SQL directly (for schema creation)"""
        cursor = self.conn.cursor()
        # Handle multiple statements
        for statement in sql.split(';'):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)
        self.conn.commit()
        
    async def batch(self, statements: List[MockD1PreparedStatement]) -> List[MockD1Result]:
        """Execute multiple statements in a batch"""
        results = []
        for stmt in statements:
            result = await stmt.run()
            results.append(result)
        return results
        
    async def _execute_sql(self, sql: str, params: List[Any]) -> List[Dict]:
        """Execute SQL and return results as list of dicts"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute(sql, params)
            
            if sql.strip().upper().startswith('SELECT'):
                # Return all rows as dicts
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            elif sql.strip().upper().startswith('INSERT'):
                # For INSERT, return the new record with generated ID
                self.conn.commit()
                last_id = cursor.lastrowid
                if last_id:
                    # Try to fetch the inserted record
                    table_name = self._extract_table_name(sql)
                    if table_name:
                        try:
                            cursor.execute(f"SELECT * FROM {table_name} WHERE rowid = ?", [last_id])
                            row = cursor.fetchone()
                            if row:
                                return [dict(row)]
                        except sqlite3.Error:
                            # Table might not have rowid, just return the ID
                            pass
                return [{'id': last_id}] if last_id else []
            else:
                # UPDATE/DELETE
                self.conn.commit()
                return []
                
        except sqlite3.Error as e:
            raise Exception(f"Database error: {e}")
            
    def _extract_table_name(self, sql: str) -> Optional[str]:
        """Extract table name from INSERT statement"""
        import re
        match = re.search(r'INSERT\s+(?:OR\s+REPLACE\s+)?INTO\s+(\w+)', sql, re.IGNORECASE)
        return match.group(1) if match else None
        
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()


def d1_unwrap(obj) -> Dict[str, Any]:
    """Mock version of d1_unwrap that works with MockD1Result"""
    if isinstance(obj, MockD1Result):
        return obj.to_py()
    elif isinstance(obj, dict):
        return obj
    elif hasattr(obj, 'to_py'):
        return obj.to_py()
    elif hasattr(obj, 'keys'):
        return {key: obj[key] for key in obj.keys()}
    else:
        return {}


def d1_unwrap_results(results) -> List[Dict[str, Any]]:
    """Mock version of d1_unwrap_results that works with MockD1Result"""
    if isinstance(results, MockD1Result):
        return results.results
    elif hasattr(results, 'results'):
        return [d1_unwrap(row) for row in results.results]
    elif isinstance(results, list):
        return [d1_unwrap(row) for row in results]
    else:
        return [d1_unwrap(results)]