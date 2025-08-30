#!/bin/bash
# Kinglet ORM Deployment Script
# Demonstrates the recommended deployment pattern

set -e  # Exit on error

echo "🚀 Kinglet ORM Deployment"
echo "========================"

# Step 1: Generate schema from models
echo "📝 Generating schema..."
cat > models.py << 'EOF'
from kinglet import Model, StringField, IntegerField, BooleanField, DateTimeField, JSONField

class Game(Model):
    title = StringField(max_length=200, null=False)
    description = StringField()
    score = IntegerField(default=0)
    is_published = BooleanField(default=False)
    created_at = DateTimeField(auto_now_add=True)
    metadata = JSONField(default=dict)

    class Meta:
        table_name = "games"

class User(Model):
    email = StringField(max_length=255, unique=True, null=False)
    username = StringField(max_length=50, null=False)
    is_active = BooleanField(default=True)
    joined_at = DateTimeField(auto_now_add=True)
    profile = JSONField(default=dict)

    class Meta:
        table_name = "users"
EOF

python -m kinglet.orm_deploy generate models > schema.sql

echo "📄 Generated schema.sql:"
cat schema.sql

# Step 2: Create D1 database if needed
echo ""
echo "🗄️  Creating D1 database..."
if ! npx wrangler d1 list | grep -q "kinglet-orm-test"; then
    npx wrangler d1 create kinglet-orm-test
    echo "✅ Database created"
else
    echo "✅ Database already exists"
fi

# Step 3: Apply schema to database
echo ""
echo "🔧 Applying schema to database..."
npx wrangler d1 execute kinglet-orm-test --file=schema.sql --local

# Step 4: Deploy worker
echo ""
echo "☁️  Deploying worker..."
npx wrangler deploy

echo ""
echo "✨ Deployment complete!"
echo ""
echo "Test your deployment:"
echo "  curl https://your-worker.workers.dev/"
echo ""
echo "For development migrations:"
echo "  curl -X POST https://your-worker.workers.dev/api/_migrate \\"
echo "       -H 'X-Migration-Token: your-secret-token'"
