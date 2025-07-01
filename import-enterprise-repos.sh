#!/bin/bash

# Enterprise Framework Repository Import Script
# Imports popular enterprise web framework repositories for testing

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prereqs() {
    log_info "Checking prerequisites..."
    
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) not found. Please install with: brew install gh"
        exit 1
    fi
    
    if ! command -v glab &> /dev/null; then
        log_error "GitLab CLI (glab) not found. Please install with: brew install glab"
        exit 1
    fi
    
    if ! command -v git &> /dev/null; then
        log_error "Git not found. Please install git."
        exit 1
    fi
    
    log_info "All prerequisites satisfied."
}

# Import a single repository
import_repo() {
    local source_repo="$1"
    local target_name="$2"
    local description="$3"
    
    log_info "Importing $source_repo -> $target_name"
    
    # Clean up any existing directory
    if [ -d "$target_name" ]; then
        log_warn "Directory $target_name already exists, removing..."
        rm -rf "$target_name"
    fi
    
    # Clone from GitHub (will work without authentication for public repos)
    log_info "Cloning from GitHub..."
    if ! git clone "https://github.com/$source_repo.git" "$target_name"; then
        log_error "Failed to clone $source_repo"
        return 1
    fi
    
    cd "$target_name"
    
    # Create GitLab repository (private)
    log_info "Creating private GitLab repository..."
    if ! glab repo create "bdmckenna/$target_name" --private --description "$description"; then
        log_error "Failed to create GitLab repository $target_name"
        cd ..
        rm -rf "$target_name"
        return 1
    fi
    
    # Change remote origin to GitLab
    log_info "Setting GitLab as remote origin..."
    git remote set-url origin "https://gitlab.com/bdmckenna/$target_name.git"
    
    # Push all branches and tags
    log_info "Pushing to GitLab..."
    if ! git push -u origin --all; then
        log_error "Failed to push branches to GitLab"
        cd ..
        rm -rf "$target_name"
        return 1
    fi
    
    if ! git push -u origin --tags; then
        log_warn "Failed to push tags (continuing anyway)"
    fi
    
    cd ..
    rm -rf "$target_name"
    
    log_info "Successfully imported $source_repo as $target_name"
    return 0
}

# Test mode: single repository
if [ "$1" = "test" ]; then
    log_info "TEST MODE: Importing single Spring Boot repository"
    check_prereqs
    
    if import_repo "spring-projects/spring-petclinic" "test-spring-petclinic" "Enterprise Spring Boot test application"; then
        log_info "TEST COMPLETE! Please review the repository at:"
        log_info "https://gitlab.com/bdmckenna/test-spring-petclinic"
        log_info ""
        log_info "If everything looks good, run the analyzer on this repo:"
        log_info "python3 gitlab-web-app-analyzer.py --filter 'test-spring-petclinic'"
        log_info ""
        log_info "Then approve bulk import by running: $0 bulk"
    else
        log_error "Test import failed!"
        exit 1
    fi
    exit 0
fi

# Bulk import mode
if [ "$1" = "bulk" ]; then
    log_info "BULK IMPORT MODE: Importing enterprise framework repositories"
    check_prereqs
    
    # Enterprise repository list (22 real applications)
    # Format: "source_repo|target_name|description"
    ENTERPRISE_REPOS=(
        # Java Enterprise Applications (3)
        "shopizer-ecommerce/shopizer|test-spring-ecommerce|Spring Boot e-commerce application"
        "quarkusio/todo-demo-app|test-quarkus-microservice|Real-world Quarkus application"
        "awslabs/aws-serverless-java-container|test-java-serverless|Spring Boot on AWS Lambda"
        
        # Node.js Enterprise Applications (4)
        "hagopj13/node-express-boilerplate|test-express-ecommerce|Production Express.js application"
        "nestjs/nest-cli|test-nestjs-enterprise|Real NestJS CLI application"
        "meanjs/mean|test-mean-stack|Full-stack MongoDB/Express/Angular/Node application"
        "vendia/serverless-express|test-nodejs-serverless|Express.js on AWS Lambda"
        
        # .NET Enterprise Applications (4)
        "dotnet-architecture/eShopOnWeb|test-aspnet-ecommerce|Microsoft reference e-commerce app"
        "jasontaylordev/CleanArchitecture|test-aspnet-clean-arch|ASP.NET Core enterprise architecture"
        "dotnet-presentations/blazor-workshop|test-blazor-application|Real Blazor application workshop"
        "aws-samples/serverless-dotnet-demo|test-dotnet-serverless|ASP.NET Core on AWS Lambda"
        
        # Python Enterprise Applications (3)
        "django-cms/django-cms|test-django-cms|Production Django CMS application"
        "tiangolo/full-stack-fastapi-postgresql|test-fastapi-fullstack|Full-stack FastAPI application"
        "Miserlou/Zappa|test-python-serverless|Django serverless deployment tool"
        
        # PHP Enterprise Applications (3)
        "bagisto/bagisto|test-laravel-ecommerce|Laravel-based e-commerce platform"
        "symfony/demo|test-symfony-demo|Symfony official demo application"
        "bref-sh/bref|test-php-serverless|PHP serverless framework with examples"
        
        # Go Enterprise Applications (4)
        "eddycjy/go-gin-example|test-gin-rest-api|Complete Gin REST API application"
        "ponzu-cms/ponzu|test-go-cms|Headless CMS built with Go"
        "micro-in-cn/tutorials|test-go-microservices|Go microservices examples"
        "aws-samples/lambda-go-samples|test-go-serverless|Official AWS Go serverless examples"
    )
    
    success_count=0
    total_count=${#ENTERPRISE_REPOS[@]}
    
    log_info "Starting bulk import of $total_count repositories..."
    
    for repo_entry in "${ENTERPRISE_REPOS[@]}"; do
        IFS='|' read -r source_repo target_name description <<< "$repo_entry"
        
        if import_repo "$source_repo" "$target_name" "$description"; then
            ((success_count++))
        else
            log_error "Failed to import $source_repo, continuing..."
        fi
        
        # Small delay to be respectful to APIs
        sleep 2
    done
    
    log_info "Bulk import complete!"
    log_info "Successfully imported: $success_count/$total_count repositories"
    log_info ""
    log_info "Next steps:"
    log_info "1. Run the analyzer on all repositories:"
    log_info "   python3 gitlab-web-app-analyzer.py"
    log_info "2. Review detection accuracy for enterprise frameworks"
    log_info "3. Update test documentation with results"
    
    exit 0
fi

# Default: show usage
echo "Usage: $0 [test|bulk]"
echo ""
echo "Modes:"
echo "  test  - Import single Spring Boot repository for testing"
echo "  bulk  - Import all 21 enterprise applications (run after test approval)"
echo ""
echo "Prerequisites:"
echo "  - GitHub CLI (gh): brew install gh"
echo "  - GitLab CLI (glab): brew install glab (authenticated)"
echo "  - Git"
echo ""
echo "Examples:"
echo "  $0 test    # Test with single repository"
echo "  $0 bulk    # Import all 21 enterprise applications (after test approval)"