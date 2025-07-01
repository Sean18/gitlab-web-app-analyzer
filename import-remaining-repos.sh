#!/bin/bash

# Import Remaining Enterprise Applications
# Imports the applications that weren't completed in the previous bulk import

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
    
    # Clone from GitHub
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

log_info "IMPORTING REMAINING ENTERPRISE APPLICATIONS"

# Fixed Quarkus repository + remaining applications that weren't imported
REMAINING_REPOS=(
    # Fixed Quarkus repository
    "quarkusio/todo-demo-app|test-quarkus-todo|Real-world Quarkus todo application"
    
    # PHP Enterprise Applications (2)
    "symfony/demo|test-symfony-demo|Symfony official demo application"
    "bref-sh/bref|test-php-serverless|PHP serverless framework with examples"
    
    # Go Enterprise Applications (4)
    "eddycjy/go-gin-example|test-gin-rest-api|Complete Gin REST API application"
    "ponzu-cms/ponzu|test-go-cms|Headless CMS built with Go"
    "micro-in-cn/tutorials|test-go-microservices|Go microservices examples"
    "aws-samples/lambda-go-samples|test-go-serverless|Official AWS Go serverless examples"
)

success_count=0
total_count=${#REMAINING_REPOS[@]}

log_info "Starting import of $total_count remaining repositories..."

for repo_entry in "${REMAINING_REPOS[@]}"; do
    IFS='|' read -r source_repo target_name description <<< "$repo_entry"
    
    if import_repo "$source_repo" "$target_name" "$description"; then
        ((success_count++))
    else
        log_error "Failed to import $source_repo, continuing..."
    fi
    
    # Small delay to be respectful to APIs
    sleep 2
done

log_info "Import of remaining repositories complete!"
log_info "Successfully imported: $success_count/$total_count repositories"
log_info ""
log_info "Next steps:"
log_info "1. Run the analyzer on all repositories:"
log_info "   python3 gitlab-web-app-analyzer.py --filter 'test-'"
log_info "2. Review detection accuracy for all enterprise frameworks"