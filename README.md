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

### Analyze Specific Repositories from File
```bash
python3 gitlab-web-app-analyzer.py --gitlab-url https://gitlab.com --token YOUR_GITLAB_TOKEN --input-file repos.txt
```

Example `repos.txt` format:
```
# One repository URL or path per line
https://gitlab.com/group1/webapp1
https://gitlab.com/group2/webapp2
group3/webapp3
# Comments and blank lines are ignored
```

## Testing

Run the regression test suite to validate detection accuracy:

```bash
./simple-test.sh YOUR_GITLAB_TOKEN
```

This tests 44 web applications across multiple frameworks and should show 100% detection rate.

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

## CLI Options

```
--gitlab-url TEXT        GitLab instance URL (or set GITLAB_URL env var)
--token TEXT            Personal access token (or set GITLAB_TOKEN env var)
--output TEXT           Output CSV filename (default: timestamp-based)
--filter TEXT           Repository name filter (default: all repositories)
--rate-limit FLOAT      Requests per second (default: 20)
--debug                 Enable debug logging for performance analysis
--no-rate-limit         Disable rate limiting (for testing)
--max-depth INTEGER     Maximum directory depth to search (default: 2)
--max-projects INTEGER  Maximum number of projects to analyze (default: 1000)
--preview               Show first 10 repositories that would be analyzed
--preview-all           Show all repositories that would be analyzed
--input-file TEXT       Input file containing repository URLs/paths (one per line)
--help                  Show help message and exit
```

## Performance

- **Target**: 1000 repositories in 30 minutes
- **Rate Limit**: 20 requests/second (default)
- **Current Test**: 44 apps analyzed with 100% detection rate