# GitLab Web App Analyzer

A Python script that analyzes GitLab repositories to identify web applications and their technology stacks. Automatically detects 15+ frameworks across Java, Node.js, .NET, Python, PHP, and Go.

## Features

- **Comprehensive Detection**: Identifies Spring Boot, Express.js, ASP.NET Core, Django, Laravel, Gin, and more
- **Multi-Framework Support**: Detects frontend + backend combinations (e.g., Angular + ASP.NET Core)
- **Performance Optimized**: Handles 1000+ repositories efficiently
- **CSV Output**: Excel-friendly format with detailed analysis results

## Installation

```bash
pip3 install -r requirements.txt
```

## Usage

### Analyze All Repositories
```bash
python3 gitlab-web-app-analyzer.py --gitlab-url https://gitlab.com --token YOUR_GITLAB_TOKEN
```

### Analyze Specific Repository
```bash
python3 gitlab-web-app-analyzer.py --gitlab-url https://gitlab.com --token YOUR_GITLAB_TOKEN --filter "repo-name"
```

### Set Output File
```bash
python3 gitlab-web-app-analyzer.py --gitlab-url https://gitlab.com --token YOUR_GITLAB_TOKEN --output my-analysis.csv
```

## Testing

Run the regression test suite to validate detection accuracy:

```bash
./simple-test.sh YOUR_GITLAB_TOKEN
```

This tests 34 web applications across multiple frameworks and should show 100% detection rate.

## Framework Detection

| Language | Frameworks Detected |
|----------|-------------------|
| **Java** | Spring Boot, Spring WebFlux, Quarkus, JAX-RS/Jersey |
| **Node.js** | Express.js, NestJS, React, Angular |
| **Python** | Django, FastAPI, Flask |
| **PHP** | Laravel, Symfony, CodeIgniter 4 |
| **Go** | Gin, Go HTTP, Go Micro, AWS Lambda Go |
| **.NET** | ASP.NET Core, Blazor, ASP.NET Framework |

## Output Format

CSV file with columns:
- Repository Name, URL, Is Web App, Confidence Level
- Web App Type, Frontend/Backend Framework, Package Manager
- Languages, Date Created, Detection Notes

## Performance

- **Target**: 1000 repositories in 30 minutes
- **Rate Limit**: 5 requests/second
- **Current Test**: 34 apps analyzed in 198 seconds (100% detection rate)