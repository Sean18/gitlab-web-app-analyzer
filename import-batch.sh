#!/bin/bash

# Batch Repository Import Script
# Imports multiple GitHub repositories to GitLab using import-single-repo.sh
# Usage: ./import-batch.sh <gitlab-token>

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[BATCH]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[BATCH]${NC} $1"
}

log_error() {
    echo -e "${RED}[BATCH]${NC} $1"
}

# Check parameters
if [ $# -eq 0 ]; then
    echo "Batch Repository Import Script"
    echo "Usage: $0 <gitlab-token>"
    echo ""
    echo "Examples:"
    echo "  $0 glpat-xxxxxxxxxxxx"
    echo ""
    echo "Prerequisites:"
    echo "  - GitLab CLI (glab): brew install glab"
    echo "  - Git"
    echo "  - Valid GitLab Personal Access Token"
    echo "  - import-single-repo.sh in current directory"
    exit 1
fi

GITLAB_TOKEN="$1"

# Check if import-single-repo.sh exists
if [ ! -f "./import-single-repo.sh" ]; then
    log_error "import-single-repo.sh not found in current directory"
    exit 1
fi

# Make sure import-single-repo.sh is executable
chmod +x ./import-single-repo.sh

log_info "Starting batch import of repositories..."

# Repository URLs to import
# Format: "github-url|optional-target-name"
# Comment out lines for repos that are already imported
REPOS=(
    # EXISTING REPOS (already imported - commented out)
    # Java Enterprise Applications
    # "https://github.com/shopizer-ecommerce/shopizer|test-spring-ecommerce"
    # "https://github.com/spring-projects/spring-petclinic|test-spring-petclinic"
    # "https://github.com/quarkusio/todo-demo-app|test-quarkus-todo"
    # "https://github.com/awslabs/aws-serverless-java-container|test-java-serverless"
    
    # Node.js Enterprise Applications
    # "https://github.com/hagopj13/node-express-boilerplate|test-express-ecommerce"
    # "https://github.com/meanjs/mean|test-mean-stack"
    # "https://github.com/vendia/serverless-express|test-nodejs-serverless"
    
    # .NET Enterprise Applications
    # "https://github.com/dotnet-architecture/eShopOnWeb|test-aspnet-ecommerce"
    # "https://github.com/jasontaylordev/CleanArchitecture|test-aspnet-clean-arch"
    # "https://github.com/dotnet-presentations/blazor-workshop|test-blazor-application"
    
    # Python Enterprise Applications
    # "https://github.com/django-cms/django-cms|test-django-cms"
    # "https://github.com/tiangolo/full-stack-fastapi-postgresql|test-fastapi-fullstack"
    # Note: Flask serverless was handled separately in original script
    
    # PHP Enterprise Applications
    # "https://github.com/symfony/demo|test-symfony-demo"
    # "https://github.com/bref-sh/bref|test-php-serverless"
    # "https://github.com/ozarnet/ci4sampleapp|test-codeigniter-app"
    # "https://github.com/invoiceninja/invoiceninja|test-laravel-invoice-ninja"
    
    # Go Enterprise Applications
    # "https://github.com/eddycjy/go-gin-example|test-gin-rest-api"
    # "https://github.com/ponzu-cms/ponzu|test-go-cms"
    # "https://github.com/aws-samples/serverless-go-demo|test-go-serverless"
    
    # NEW REPOS TO IMPORT (uncomment and modify as needed)
    # Additional diverse web applications for testing
    
    # ASP.NET Core Web API
    #"https://github.com/FabianGosebrink/ASPNETCore-WebAPI-Sample|test-aspnet-core-webapi-sample"
    
    # ASP.NET Core MVC
    #"https://github.com/dotnet-architecture/eShopOnWeb|test-aspnet-core-mvc-eshop"
    
    # Blazor Server
    #"https://github.com/JeremyLikness/BlazorServerEFCoreExample|test-blazor-server-efcore"
    
    # Blazor WebAssembly
    #"https://github.com/JeremyLikness/BlazorWasmEFCoreExample|test-blazor-wasm-efcore"
    
    # ASP.NET Framework MVC (Legacy)
    #"https://github.com/izhub/EF6MVC5Example|test-aspnet-mvc5-ef6"
    
    # ASP.NET Framework Web API (Legacy)
    #"https://github.com/kiewic/AspNet-WebApi-Sample|test-aspnet-webapi-legacy"
    
    # Minimal APIs (.NET 6+)
    #"https://github.com/cornflourblue/dotnet-6-minimal-api|test-dotnet-minimal-api"

     

    #     aws-lambda-java-example: 
    #   ✅ Web App: YES
    #   ✅ Type: Java
    #   ✅ Framework: AWS Lambda
    #   ✅ Evidence: aws-lambda-java-core in pom.xml
    "https://github.com/aws-samples/lambda-java8-dynamodb|test-lambda-java8-dynamodb"

    # app-service-java-quickstart:
    #   ✅ Web App: YES  
    #   ✅ Type: Java
    #   ✅ Framework: Azure App
    #   ✅ Evidence: azure-webapp-maven-plugin + Spring Boot
    "https://github.com/Azure-Samples/app-service-java-quickstart|test-app-service-java-quickstart"

    # spring-mvc-showcase:
    #   ✅ Web App: YES
    #   ✅ Type: Java  
    #   ✅ Framework: Spring MVC 
    #   ✅ Evidence: WAR packaging + servlet-api
    "https://github.com/spring-projects/spring-mvc-showcase|test-spring-mvc-showcase"

    # play-java-starter-example:
    #   ✅ Web App: YES
    #   ✅ Type: Java
    #   ✅ Framework: Play Framework
    #   ✅ Evidence: build.sbt + Play dependencies
    #"https://github.com/playframework/play-samples/tree/3.0.x/play-java-starter-example|test-play-java-starter-example"
)

# Counters
success_count=0
skip_count=0
fail_count=0
total_count=${#REPOS[@]}

log_info "Processing $total_count repositories..."

# Process each repository
for i in "${!REPOS[@]}"; do
    repo_entry="${REPOS[$i]}"
    
    # Skip empty lines
    if [ -z "$repo_entry" ]; then
        continue
    fi
    
    # Parse repo entry
    IFS='|' read -r github_url target_name <<< "$repo_entry"
    
    log_info "[$((i+1))/$total_count] Processing: $github_url"
    
    # Call import-single-repo.sh
    if [ -n "$target_name" ]; then
        # Use custom target name
        if ./import-single-repo.sh "$GITLAB_TOKEN" "$github_url" "$target_name"; then
            ((success_count++))
        else
            ((fail_count++))
            log_error "Failed to import $github_url"
        fi
    else
        # Use default target name
        if ./import-single-repo.sh "$GITLAB_TOKEN" "$github_url"; then
            ((success_count++))
        else
            ((fail_count++))
            log_error "Failed to import $github_url"
        fi
    fi
    
    # Small delay to be respectful to APIs
    sleep 2
done

# Summary
log_info "Batch import complete!"
log_info "Results:"
log_info "  ✅ Successfully imported: $success_count"
log_info "  ⏭️  Skipped (already exist): $skip_count"
log_info "  ❌ Failed: $fail_count"
log_info "  📊 Total processed: $total_count"

if [ $fail_count -gt 0 ]; then
    log_warn "Some imports failed. Check the logs above for details."
    exit 1
else
    log_info "All imports completed successfully!"
    exit 0
fi