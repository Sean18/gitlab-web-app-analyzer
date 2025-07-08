#!/bin/bash

# Single Repository Import Script
# Imports a single GitHub repository to GitLab (private)
# Usage: ./import-single-repo.sh <gitlab-token> <github-url> [target-name]

set -e  # Exit on any error

# Configuration
GITLAB_URL="https://gitlab.com"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_skip() {
    echo -e "${BLUE}[SKIP]${NC} $1"
}

# Check prerequisites
check_prereqs() {
    local gitlab_token="$1"
    
    if ! command -v glab &> /dev/null; then
        log_error "GitLab CLI (glab) not found. Please install with: brew install glab"
        exit 1
    fi
    
    if ! command -v git &> /dev/null; then
        log_error "Git not found. Please install git."
        exit 1
    fi
    
    if [ -z "$gitlab_token" ]; then
        log_error "GitLab token is required"
        exit 1
    fi
    
    # Set GitLab token for authentication
    export GITLAB_TOKEN="$gitlab_token"
    
    # Get GitLab username from token
    GITLAB_USERNAME=$(glab api user --method GET | grep -o '"username":"[^"]*' | cut -d'"' -f4 2>/dev/null || echo "")
    if [ -z "$GITLAB_USERNAME" ]; then
        log_error "Failed to get GitLab username. Please check your token."
        exit 1
    fi
    
    log_info "GitLab username: $GITLAB_USERNAME"
}

# Extract repository name from GitHub URL
extract_repo_name() {
    local url="$1"
    # Remove .git suffix if present
    url="${url%.git}"
    # Extract owner/repo from URL
    echo "$url" | sed -n 's|.*github\.com/||p'
}

# Extract just the repo name (without owner)
extract_target_name() {
    local owner_repo="$1"
    echo "$owner_repo" | cut -d'/' -f2
}

# Check if GitLab repository already exists
gitlab_repo_exists() {
    local repo_name="$1"
    if glab repo view "$GITLAB_USERNAME/$repo_name" &> /dev/null; then
        return 0  # exists
    else
        return 1  # doesn't exist
    fi
}

# Main import function
import_repo() {
    local github_url="$1"
    local target_name="$2"
    
    # Extract repo info from URL
    local owner_repo=$(extract_repo_name "$github_url")
    if [ -z "$owner_repo" ]; then
        log_error "Invalid GitHub URL: $github_url"
        return 1
    fi
    
    # Use provided target name or default to repo name
    if [ -z "$target_name" ]; then
        target_name=$(extract_target_name "$owner_repo")
    fi
    
    log_info "Processing: $owner_repo -> $target_name"
    
    # Check if GitLab repo already exists
    if gitlab_repo_exists "$target_name"; then
        log_skip "Repository $target_name already exists in GitLab"
        return 0
    fi
    
    log_info "Importing $owner_repo to GitLab as $target_name"
    
    # Clean up any existing directory
    if [ -d "$target_name" ]; then
        log_warn "Directory $target_name already exists, removing..."
        rm -rf "$target_name"
    fi
    
    # Clone from GitHub
    log_info "Cloning from GitHub..."
    if ! git clone "$github_url" "$target_name"; then
        log_error "Failed to clone $github_url"
        return 1
    fi
    
    cd "$target_name"
    
    # Create private GitLab repository
    log_info "Creating private GitLab repository..."
    if ! glab repo create "$GITLAB_USERNAME/$target_name" --private --description "Imported from $github_url"; then
        log_error "Failed to create GitLab repository $target_name"
        cd ..
        rm -rf "$target_name"
        return 1
    fi
    
    # Change remote origin to GitLab
    log_info "Setting GitLab as remote origin..."
    git remote set-url origin "$GITLAB_URL/$GITLAB_USERNAME/$target_name.git"
    
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
    
    log_info "Successfully imported $owner_repo as $target_name"
    return 0
}

# Main script
main() {
    if [ $# -lt 2 ]; then
        echo "Single Repository Import Script"
        echo "Usage: $0 <gitlab-token> <github-url> [target-name]"
        echo ""
        echo "Examples:"
        echo "  $0 glpat-xxxxxxxxxxxx https://github.com/owner/repo"
        echo "  $0 glpat-xxxxxxxxxxxx https://github.com/owner/repo my-custom-name"
        echo ""
        echo "Prerequisites:"
        echo "  - GitLab CLI (glab): brew install glab"
        echo "  - Git"
        echo "  - Valid GitLab Personal Access Token"
        exit 1
    fi
    
    local gitlab_token="$1"
    local github_url="$2"
    local target_name="$3"
    
    check_prereqs "$gitlab_token"
    import_repo "$github_url" "$target_name"
}

main "$@"