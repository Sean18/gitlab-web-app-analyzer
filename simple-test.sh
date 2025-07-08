#!/bin/sh

# Simple Enterprise Regression Test  
# Tests all web applications for detection (excluding deleted repos)

set -e

# Configuration
GITLAB_URL="${GITLAB_URL:-https://gitlab.com}"
GITLAB_TOKEN="$1"
OUTPUT_FILE="test-results.csv"

# All web applications from latest analysis (excluding deleted repos)
# Using array to properly handle names with spaces
TEST_APPS=(
"test-laravel-invoice-ninja"
"test-codeigniter-app"
"test-python-serverless"
"test-go-serverless"
"test-go-cms"
"test-gin-rest-api"
"test-symfony-demo"
"test-quarkus-todo"
"test-fastapi-fullstack"
"test-django-cms"
"test-dotnet-serverless"
"test-blazor-application"
"test-aspnet-clean-arch"
"test-aspnet-ecommerce"
"test-nodejs-serverless"
"test-mean-stack"
"test-express-ecommerce"
"test-java-serverless"
"test-spring-ecommerce"
"test-spring-petclinic"
"Umbraco CMS"
"Dnn.Platform"
"BlogEngine.NET"
"NopCommerce"
"OrchardCore"
"Hippotech 2.0 Github"
"WebGoat"
"Juice Shop"
"Gs Reactive Rest Service"
"Node Express Realworld Example App"
"Spring Petclinic"
"Go Gin Example"
"Laravel"
"Flask"
)

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

if ! command -v bc &> /dev/null; then
    echo "Error: bc command not found. Please install bc for performance calculations."
    echo "  macOS: brew install bc"
    echo "  Ubuntu/Debian: sudo apt-get install bc"
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

# Extract repository count from CSV output file (more reliable than parsing console output)
if [ -f "$OUTPUT_FILE" ]; then
    total_repos=$(tail -n +2 "$OUTPUT_FILE" | wc -l | xargs)  # Count CSV rows minus header
    if [ -z "$total_repos" ] || [ "$total_repos" -eq 0 ]; then
        total_repos=1  # Fallback to prevent division by zero
    fi
else
    total_repos=1  # Fallback if CSV file not found
fi

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

for app in "${TEST_APPS[@]}"; do
    if [ -n "$app" ]; then  # Skip empty entries
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

# Performance benchmark calculations
seconds_per_repo=$(echo "scale=2; $execution_time / $total_repos" | bc)
minutes_per_1000=$(echo "scale=1; ($seconds_per_repo * 1000) / 60" | bc)
target_minutes=30.0
target_seconds_per_repo=1.8

echo ""
echo "Performance Benchmark:"
echo "===================="
echo "Total repositories analyzed: $total_repos"
echo "Average per repository: ${seconds_per_repo}s"
echo "Projected for 1000 repos: ${minutes_per_1000} minutes"
echo "Performance target: ${target_minutes} minutes (${target_seconds_per_repo}s per repo)"

# Performance pass/fail logic
performance_pass=$(echo "$seconds_per_repo <= $target_seconds_per_repo" | bc)
if [ "$performance_pass" -eq 1 ]; then
    echo "Performance result: ✅ PASS"
    performance_status="PASS"
else
    echo "Performance result: ❌ FAIL"
    performance_status="FAIL"
fi

# Final result
echo ""
detection_success=$([ $FAILED -eq 0 ] && echo "true" || echo "false")
performance_success=$([ "$performance_status" = "PASS" ] && echo "true" || echo "false")

if [ "$detection_success" = "true" ] && [ "$performance_success" = "true" ]; then
    echo "🎉 SUCCESS: All tests passed!"
    echo "✅ Detection: All enterprise applications detected (100%)"
    echo "✅ Performance: Meets 30-minute target for 1000 repos"
    echo "GitLab Web App Analyzer is working correctly."
    exit 0
elif [ "$detection_success" = "true" ] && [ "$performance_success" = "false" ]; then
    echo "⚠️  PARTIAL SUCCESS: Detection passed, performance failed"
    echo "✅ Detection: All enterprise applications detected (100%)"
    echo "❌ Performance: Exceeds 30-minute target for 1000 repos"
    echo "Consider optimizing analyzer performance."
    exit 1
else
    echo "❌ FAILURE: Detection test failed"
    echo "❌ Detection: $FAILED applications not detected"
    if [ "$performance_success" = "false" ]; then
        echo "❌ Performance: Exceeds 30-minute target for 1000 repos"
    else
        echo "✅ Performance: Meets 30-minute target for 1000 repos"
    fi
    echo ""
    echo "Please investigate the following:"
    
    # Show which apps failed
    echo ""
    echo "Failed applications:"
    for app in "${TEST_APPS[@]}"; do
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