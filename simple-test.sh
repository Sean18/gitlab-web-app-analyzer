#!/bin/sh

# Simple Enterprise Regression Test  
# Tests all web applications for detection (excluding deleted repos)

set -e

# Configuration
GITLAB_URL="${GITLAB_URL:-https://gitlab.com}"
GITLAB_TOKEN="$1"
OUTPUT_FILE="test-results.csv"

# All web applications from latest analysis (excluding deleted repos)
TEST_APPS="
test-laravel-invoice-ninja
test-codeigniter-app
test-python-serverless
test-go-serverless
test-go-cms
test-gin-rest-api
test-symfony-demo
test-quarkus-todo
test-fastapi-fullstack
test-django-cms
test-dotnet-serverless
test-blazor-application
test-aspnet-clean-arch
test-aspnet-ecommerce
test-nodejs-serverless
test-mean-stack
test-express-ecommerce
test-java-serverless
test-spring-ecommerce
test-spring-petclinic
Umbraco CMS
Dnn.Platform
BlogEngine.NET
NopCommerce
OrchardCore
Hippotech 2.0 Github
WebGoat
Juice Shop
Gs Reactive Rest Service
Node Express Realworld Example App
Spring Petclinic
Go Gin Example
Laravel
Flask
"

# Check prerequisites
if [ -z "$GITLAB_TOKEN" ]; then
    echo "Usage: $0 GITLAB_TOKEN"
    echo "Example: $0 glpat-xyz123"
    exit 1
fi

if [ ! -f "gitlab-web-app-analyzer.py" ]; then
    echo "Error: gitlab-web-app-analyzer.py not found"
    exit 1
fi

echo "Simple Enterprise Regression Test"
echo "================================="
echo "Testing all web applications for detection (excluding deleted repos)"
echo ""

# Run analyzer on all repositories
echo "Running GitLab Web App Analyzer on all repositories..."
start_time=$(date +%s)

python3 gitlab-web-app-analyzer.py --gitlab-url "$GITLAB_URL" --token "$GITLAB_TOKEN" --output "$OUTPUT_FILE"

end_time=$(date +%s)
execution_time=$((end_time - start_time))

echo "Analyzer completed in ${execution_time}s"
echo ""

# Check if results file exists
if [ ! -f "$OUTPUT_FILE" ]; then
    echo "Error: Results file not found: $OUTPUT_FILE"
    exit 1
fi

# Check each enterprise test application
echo "Checking enterprise test applications:"
echo "======================================"
PASSED=0
FAILED=0
TOTAL=0

for app in $TEST_APPS; do
    app=$(echo "$app" | xargs)  # Trim whitespace
    if [ -n "$app" ]; then  # Skip empty lines
        ((TOTAL++))
        if grep -q "$app.*,YES," "$OUTPUT_FILE"; then
            echo "✅ $app: DETECTED"
            ((PASSED++))
        else
            echo "❌ $app: NOT DETECTED"
            ((FAILED++))
        fi
    fi
done

echo ""
echo "Summary:"
echo "========"
echo "Applications tested: $TOTAL"
echo "Detected as web apps: $PASSED"
echo "Not detected: $FAILED"
echo "Detection rate: $((PASSED * 100 / TOTAL))%"
echo "Execution time: ${execution_time}s"

# Final result
if [ $FAILED -eq 0 ]; then
    echo ""
    echo "🎉 SUCCESS: All enterprise applications detected!"
    echo "GitLab Web App Analyzer is working correctly."
    exit 0
else
    echo ""
    echo "❌ FAILURE: $FAILED applications not detected"
    echo "Please investigate the following:"
    
    # Show which apps failed
    echo ""
    echo "Failed applications:"
    for app in $TEST_APPS; do
        app=$(echo "$app" | xargs)
        if [ -n "$app" ]; then
            if ! grep -q "$app.*,YES," "$OUTPUT_FILE"; then
                echo "  - $app"
            fi
        fi
    done
    
    echo ""
    echo "Results saved to: $OUTPUT_FILE"
    exit 1
fi