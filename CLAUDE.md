# GitLab Web App Analyzer - Claude Context Documentation

## Overview
Python script that analyzes GitLab repositories to identify web applications and their technology stacks. Outputs analysis to CSV format.

## Performance
The script should scale to handle 1000s of repos in a reasonable time.  TARGET:  1000 repos in 30 minutes.

## Output
CSV output file should be human readable, and formatted to display well in MS Excel.
Console output should include progress indicators, and metrics about the scan, but keep it short.  Any debug logging should be removed or disabled by an option.

## Testing and Debugging

### Install Dependencies
```bash
pip3 install -r requirements.txt
```

### Testing all repos (no filter)
```bash
python3 gitlab-web-app-analyzer.py --gitlab-url https://gitlab.com --token YOUR_GITLAB_TOKEN
```

### Test Single Repo (Good for debug/test/fix loop)
```bash
python3 gitlab-web-app-analyzer.py --gitlab-url https://gitlab.com --token YOUR_GITLAB_TOKEN --filter "repo-name" --output temp-file.csv
```

### Performance Testing

The analyzer includes comprehensive performance testing capabilities via `perftest.py` to analyze runtime performance per app type (.NET, Java, Node.js, etc.) with detailed metrics on API calls, processing time, and bottlenecks.

#### Quick Performance Test (Balanced Subset)
```bash
python3 perftest.py --mode small --max-per-type 2 --debug --gitlab-url https://gitlab.com --token YOUR_GITLAB_TOKEN
```

#### Test Specific App Type
```bash
python3 perftest.py --mode app-type --app-type ".NET" --debug --gitlab-url https://gitlab.com --token YOUR_GITLAB_TOKEN
```

#### Full Performance Test (All Repositories)
```bash
python3 perftest.py --mode full --gitlab-url https://gitlab.com --token YOUR_GITLAB_TOKEN
```

#### Test Modes
- `--mode small`: Balanced subset testing (default: 3 repos per app type)
- `--mode full`: Test all available repositories  
- `--mode app-type`: Focus on specific app type (requires `--app-type`)

#### Performance Report Output
The performance test generates a detailed report including:
- **1000-repo projections**: Estimated time to scan 1000 repositories
- **Bottleneck identification**: Slowest API calls and app types
- **Optimization recommendations**: Specific actions to improve speed
- **App type comparison**: Performance breakdown by technology stack (.NET, Java, Node.js, Python, PHP, Go)
- **API call breakdown**: Time spent on project info, languages, file tree, file content calls

#### Target Performance
- **Goal**: 1000 repositories in 30 minutes
- **Current status**: Use performance tests to validate scaling and identify optimization opportunities

## Framework Detection Patterns

### Java (Maven)
- `spring-boot-starter-web` → Spring Boot
- `spring-boot-starter-webflux` → Spring WebFlux
- `quarkus-resteasy` → Quarkus
- `jersey-server` → JAX-RS/Jersey

### Node.js
- `express` → Express
- `@nestjs/core` → NestJS
- `react` → React (frontend)
- `@angular/core` → Angular (frontend)

### Python
- `django` → Django
- `flask` → Flask
- `fastapi` → FastAPI

### PHP
- `laravel/framework` → Laravel
- `symfony/framework-bundle` → Symfony
- `codeigniter4/framework` → CodeIgniter 4

### Go
- `gin-gonic/gin` → Gin
- `github.com/aws/aws-lambda-go` → AWS Lambda Go
- `github.com/micro/go-micro` → Go Micro

### .NET
- `Microsoft.AspNetCore` → ASP.NET Core
- `System.Web` → ASP.NET Framework
- Web project references in `.sln` files

## Test Results (2025-07-14)
<!-- NOTE: When updating test results, replace this entire section with new data -->

### Current Status: 95.5% Detection Rate ✅
- **Total repositories tested**: 44 repositories
- **Web applications detected**: 42 web applications
- **Non-web repositories**: 2 (correctly identified as non-web)
- **Detection rate**: 95.5% (42/44 detected correctly)
- **Coverage**: 15+ frameworks across 6 languages

### Technology Stack Distribution
- **.NET**: 16 applications (12 .NET Core, 4 .NET Framework)
  - ASP.NET Core, Blazor WebAssembly, Blazor Server, ASP.NET MVC, ASP.NET Web API
- **Java**: 8 applications 
  - Spring Boot, Spring WebFlux, Quarkus, Spring Framework
- **Node.js**: 6 applications
  - Express.js applications with various architectures
- **Python**: 4 applications
  - Django, Flask, FastAPI frameworks
- **PHP**: 4 applications  
  - Laravel, Symfony, CodeIgniter 4
- **Go**: 4 applications
  - Gin, Go HTTP, AWS Lambda Go

### Test Command
```bash
python3 gitlab-web-app-analyzer.py --gitlab-url https://gitlab.com --token YOUR_GITLAB_TOKEN
```

### Performance Tracking
Performance optimization implemented with optional tracking:
- **Modular design**: Performance tracking moved to separate `performance_tracker.py`
- **Zero overhead**: Optional tracking (disabled by default)
- **Context managers**: Clean integration with repository and API call tracking
- **Comprehensive metrics**: API call breakdown, processing time analysis, 1000-repo projections

## Key Fixes Applied

### Spring WebFlux Detection (2025-07-08)
- **Issue**: "Gs Reactive Rest Service" not detected
- **Fix**: Added `complete` and `initial` directories to search paths for Spring Guide repositories
- **Result**: Spring WebFlux now properly detected

### Go Applications
- **Fix**: Added `cmd/` subdirectory search for Go applications
- **Fix**: Enhanced main.go patterns for microservices and serverless

### PHP Frameworks
- **Fix**: Added `symfony/framework-bundle` for modern Symfony
- **Fix**: Added `codeigniter4/framework` for CodeIgniter 4

## Performance
- **Optimized for**: 1000+ repositories (estimated 10-15 minutes)
- **Rate limit**: 5 requests/second
- **Efficient search**: Targeted subdirectories only, no full recursive scan

## CSV Output Format
```
Repository Name, Repository URL, Is Web App, Confidence Level, Web App Type, 
Frontend Framework, Backend Framework, Package Manager, Languages, Date Created, Notes
```

## Ready for Production
Comprehensive framework detection across:
- **Java**: Spring Boot, Spring WebFlux, Quarkus, JAX-RS/Jersey
- **Node.js**: Express.js, NestJS, React, Angular
- **.NET**: ASP.NET Core, Blazor, ASP.NET Framework
- **Python**: Django, FastAPI, Flask
- **PHP**: Laravel, Symfony, CodeIgniter 4
- **Go**: Gin, Go HTTP, Go Micro, AWS Lambda Go