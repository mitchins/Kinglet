# Test Infrastructure Improvement Analysis

## Current State Assessment
- **598 mock occurrences** across 18 test files
- **~50+ repeated d1_unwrap patch blocks**
- **No conftest.py or centralized fixtures**
- **Mixed abstraction levels** (MockD1Database + function patches)

## Improvement Matrix: [Desirability × Value] / Feasibility

| Improvement | Desirability (1-10) | Value (1-10) | Feasibility (1-10) | Score | Priority |
|-------------|---------------------|---------------|-------------------|-------|----------|
| **Create conftest.py with d1_unwrap fixtures** | 9 | 8 | 9 | 7.11 | 🔥 HIGH |
| **Base test classes for ORM tests** | 7 | 7 | 8 | 6.13 | 🔥 HIGH |
| **Centralize MockD1Database fixture** | 8 | 6 | 9 | 5.33 | 🟡 MED |
| **Consolidate multi-module patches** | 6 | 8 | 7 | 6.86 | 🟡 MED |
| **Dependency injection at storage layer** | 9 | 9 | 4 | 20.25 | 🔴 LOW |
| **Auto-patch decorators** | 5 | 5 | 8 | 3.13 | 🔴 LOW |
| **Mock registry pattern** | 7 | 6 | 5 | 8.40 | 🔴 LOW |
| **Test data factories** | 6 | 7 | 7 | 6.00 | 🟡 MED |

## Detailed Analysis

### 🔥 HIGH PRIORITY

#### 1. Create conftest.py with d1_unwrap fixtures
**Score: 7.11** | **ROI: Immediate**
```python
# tests/conftest.py
@pytest.fixture(autouse=True)
def d1_patches():
    patches = [
        patch('kinglet.orm.d1_unwrap', d1_unwrap),
        patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results),
        patch('kinglet.orm_migrations.d1_unwrap', d1_unwrap),
        patch('kinglet.orm_migrations.d1_unwrap_results', d1_unwrap_results),
    ]
    for p in patches: p.start()
    yield
    for p in patches: p.stop()
```
**Impact:** Eliminates ~50 boilerplate blocks immediately

#### 2. Base test classes for ORM tests
**Score: 6.13** | **ROI: High**
```python
class BaseORMTest:
    @pytest.fixture(autouse=True)
    def setup_mock_db(self):
        self.mock_db = MockD1Database()
```
**Impact:** Standardizes test setup, reduces setup code by ~60%

### 🟡 MEDIUM PRIORITY

#### 3. Centralize MockD1Database fixture
**Score: 5.33**
- Simple implementation
- Moderate cleanup benefit
- Low risk

#### 4. Consolidate multi-module patches
**Score: 6.86**
- High cleanup value
- Moderate complexity due to module boundaries
- Worth doing after conftest.py

#### 8. Test data factories
**Score: 6.00**
```python
class GameFactory:
    @staticmethod
    def create(**kwargs):
        defaults = {'title': 'Test Game', 'score': 100}
        return SampleGame(**{**defaults, **kwargs})
```

### 🔴 LOW PRIORITY

#### 5. Dependency injection at storage layer
**Score: 20.25** (High value, low feasibility)
- Would eliminate all patches
- Requires major architectural changes
- High risk, long timeline

#### 6. Auto-patch decorators
**Score: 3.13**
- Limited benefit vs effort
- Adds complexity without major gains

#### 7. Mock registry pattern
**Score: 8.40**
- Over-engineered for current needs
- Better for larger codebases

## Implementation Roadmap

### Phase 1: Quick Wins (1-2 hours)
1. Create `tests/conftest.py` with d1_unwrap fixtures
2. Remove 50+ boilerplate patch blocks
3. Add MockD1Database fixture

### Phase 2: Standardization (2-4 hours)
1. Create `BaseORMTest` class
2. Migrate test classes to inherit from base
3. Consolidate multi-module patches

### Phase 3: Enhancement (4-8 hours)
1. Add test data factories for common models
2. Create specialized fixtures for migration tests
3. Documentation and usage guidelines

## Expected Outcomes

### After Phase 1:
- **70% reduction** in boilerplate code
- **Zero breaking changes** to existing tests
- **Immediate maintainability improvement**

### After Phase 2:
- **Standardized test patterns** across all ORM tests
- **Easier onboarding** for new test development
- **Consistent mock setup** and teardown

### After Phase 3:
- **Best-in-class test infrastructure**
- **Minimal test setup code** for new features
- **Robust patterns** for future growth

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|---------|------------|
| Breaking existing tests | Low | High | Incremental migration, thorough testing |
| Over-engineering | Medium | Medium | Focus on high-value, simple solutions |
| Developer adoption | Low | Medium | Clear documentation, gradual rollout |

## Success Metrics

- **Boilerplate reduction:** Target 70% fewer mock setup lines
- **Test consistency:** 100% of ORM tests use standard patterns
- **Maintainability:** New ORM tests require <5 lines of setup
- **Developer satisfaction:** Faster test writing, clearer patterns
