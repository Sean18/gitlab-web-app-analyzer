#!/usr/bin/env python3
"""
GitLab Web App Repository Analyzer

Analyzes GitLab repositories to identify web applications, serverless functions,
and their technology stacks. Outputs comprehensive analysis to CSV format.
"""

# Suppress urllib3 NotOpenSSLWarning at the system level
import warnings
warnings.filterwarnings('ignore', message='.*urllib3 v2 only supports OpenSSL.*')

import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import click
import gitlab
import requests
from dateutil.parser import parse as parse_date
from gitlab.exceptions import GitlabError


class GitLabAnalyzer:
    """Main analyzer class for GitLab repositories"""
    
    def __init__(self, gitlab_url: str, token: Optional[str] = None, rate_limit: float = 2.0, debug: bool = False, search_depth: int = 2):
        self.gitlab_url = gitlab_url
        self.rate_limit = rate_limit
        self.last_request_time = 0
        self.debug = debug
        self.api_call_count = 0
        self.total_wait_time = 0
        self.no_rate_limit = False
        self.search_depth = search_depth  # Maximum directory depth to search
        
        # Initialize GitLab client
        if not token:
            raise click.ClickException("GitLab token is required. Provide via --token or GITLAB_TOKEN environment variable")
        
        self.gl = gitlab.Gitlab(gitlab_url, private_token=token)
        
        try:
            # Test authentication by making a simple API call
            click.echo("Testing GitLab authentication...")
            self.gl.auth()
            # Test with a simple API call
            self.gl.projects.list(per_page=1, get_all=False)
            click.echo("Authentication successful")
        except Exception as e:
            raise click.ClickException(f"GitLab authentication failed: {e}")
    
    def _rate_limit_wait(self, skip_if_cached=False):
        """Enforce rate limiting between API requests"""
        if skip_if_cached:
            return  # Skip rate limiting for cached operations
        
        # For testing: allow disabling rate limiting
        if self.no_rate_limit:
            self.api_call_count += 1
            return
            
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        min_interval = 1.0 / self.rate_limit
        
        if time_since_last < min_interval:
            wait_time = min_interval - time_since_last
            if self.debug:
                click.echo(f"Rate limiting: waiting {wait_time:.3f}s (target: {min_interval:.3f}s interval)")
            time.sleep(wait_time)
            self.total_wait_time += wait_time
        
        self.last_request_time = time.time()
        self.api_call_count += 1
    
    def _api_call_with_retry(self, api_call, max_retries=3):
        """Execute API call with retry logic for rate limit errors"""
        for attempt in range(max_retries + 1):
            try:
                result = api_call()
                
                # Check for rate limit headers if available
                if hasattr(result, '_raw') and hasattr(result._raw, 'headers'):
                    remaining = result._raw.headers.get('X-RateLimit-Remaining')
                    if remaining and int(remaining) < 100:
                        click.echo(f"Warning: Rate limit approaching - {remaining} requests remaining")
                
                return result
            except GitlabError as e:
                if hasattr(e, 'response_code') and e.response_code in [429, 503]:
                    if attempt < max_retries:
                        # Exponential backoff: 1s, 2s, 4s
                        wait_time = 2 ** attempt
                        click.echo(f"Rate limit hit, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        click.echo(f"Rate limit exceeded after {max_retries} retries")
                        raise
                else:
                    # Non-rate-limit error, re-raise immediately
                    raise
            except Exception as e:
                # Network or other errors - only retry once
                if attempt == 0:
                    time.sleep(1)
                    continue
                else:
                    raise
    
    def get_repositories(self, name_filter: Optional[str] = None) -> List[Any]:
        """Get list of repositories with optional name filtering"""
        try:
            click.echo("Fetching repositories from GitLab API...")
            self._rate_limit_wait()
            click.echo("Making API request...")
            # Get projects owned by or accessible to the authenticated user
            projects = self._api_call_with_retry(
                lambda: self.gl.projects.list(membership=True, per_page=100)
            )
            if not projects:
                projects = []
            click.echo(f"Retrieved {len(projects)} projects from API")
            
            if name_filter:
                click.echo(f"Applying filter: {name_filter}")
                projects = [p for p in projects if name_filter.lower() in p.name.lower()]
                click.echo(f"After filtering: {len(projects)} projects")
            
            return projects
        except Exception as e:
            raise click.ClickException(f"Failed to fetch repositories: {e}")
    
    def get_file_content(self, project_obj: Any, file_path: str) -> Optional[str]:
        """Get content of a file from repository using cached project object"""
        if self.debug:
            get_file_start = time.time()
        
        # Try common branch names and the project's default branch
        branch_names = ['main', 'master']
        
        # Add the project's default branch if it's different
        try:
            default_branch = project_obj.default_branch
            if default_branch and default_branch not in branch_names:
                branch_names.insert(0, default_branch)  # Try default branch first
        except:
            pass
        
        for branch_name in branch_names:
            try:
                if self.debug:
                    api_call_start = time.time()
                
                self._rate_limit_wait()
                file_info = self._api_call_with_retry(
                    lambda: project_obj.files.get(file_path, ref=branch_name)
                )
                
                if self.debug:
                    api_call_time = time.time() - api_call_start
                
                if file_info:
                    content = file_info.decode().decode('utf-8')
                    if self.debug:
                        total_time = time.time() - get_file_start
                        content_size = len(content)
                        click.echo(f"DEBUG: get_file_content('{file_path}') -> SUCCESS in {total_time:.3f}s (size: {content_size} chars, API: {api_call_time:.3f}s)")
                    return content
                else:
                    return None
            except:
                continue
        
        return None
    
    def _get_file_path(self, file_name: str) -> str:
        """Get the full path for a target file basename"""
        return self._file_path_map.get(file_name, file_name)
    
    def _is_target_file(self, file_name: str) -> bool:
        """Check if a filename matches our target web app files"""
        target_files = [
            'package.json', 'requirements.txt', 'pyproject.toml', 'pom.xml', 'build.gradle',
            'go.mod', 'main.go', 'composer.json', 'index.php', 'web.config', 'Dockerfile',
            'serverless.yml', 'host.json', 'local.settings.json', 'packages.config',
            'aws-lambda-tools-defaults.json', 'template.yaml', 'template.yml',
            # Enhanced patterns from GitHub analysis
            'Global.asax', 'Global.asax.cs', 'Startup.cs', 'Program.cs',
            'appsettings.json', 'launchSettings.json', '_Host.cshtml', 'App.razor',
            'RouteConfig.cs', 'WebApiConfig.cs', 'BundleConfig.cs', 'FilterConfig.cs'
        ]
        
        return file_name in target_files or file_name.endswith('.csproj') or file_name.endswith('.sln')
    
    def _find_relevant_files(self, project_obj: Any) -> List[str]:
        """Get files at root, level 1, and level 2 using progressive depth search"""
        found_files = []
        self._file_path_map = {}  # basename -> full_path mapping for get_file_content()
        directories_to_search = [""]  # Start with root
        
        for current_depth in range(3):  # 0=root, 1=level1, 2=level2
            next_level_dirs = []
            
            for dir_path in directories_to_search:
                self._rate_limit_wait()
                
                try:
                    # Use GitLab API with path parameter for depth control
                    query_params: Dict[str, Any] = {'recursive': False}
                    if dir_path:  # Only add path parameter if not root
                        query_params['path'] = dir_path
                    
                    items = self.gl.http_list(
                        f'/projects/{project_obj.id}/repository/tree',
                        query_data=query_params,
                        get_all=True
                    )
                    
                    for item in items:
                        if item['type'] == 'blob':  # File
                            file_name = item['name']
                            if self._is_target_file(file_name):
                                # Store basename in found_files for clean checking logic
                                if file_name not in found_files:  # Avoid duplicates
                                    found_files.append(file_name)
                                    # Map basename to full path for get_file_content()
                                    self._file_path_map[file_name] = item['path']
                        elif item['type'] == 'tree' and current_depth < 2:  # Directory
                            next_level_dirs.append(item['path'])
                            
                except Exception as e:
                    if self.debug:
                        click.echo(f"Debug: Error accessing directory '{dir_path}': {e}")
                    continue
            
            directories_to_search = next_level_dirs
            if not directories_to_search:  # No more directories to search
                break
        
        return found_files
    

    
    def analyze_repository(self, project: Any) -> Dict[str, Any]:
        """Analyze a single repository for web app characteristics"""
        try:
            repo_start_time = time.time()
            
            self._rate_limit_wait()
            api_start_time = time.time()
            full_project = self._api_call_with_retry(
                lambda: self.gl.projects.get(project.id)
            )
            api_time = time.time() - api_start_time
            
            if self.debug:
                click.echo(f"Repository '{project.name}': Project API call took {api_time:.3f}s")
            
            result = {
                'name': project.name,
                'url': project.web_url,
                'is_web_app': 'UNKNOWN',
                'confidence': 'LOW',
                'web_app_type': '',
                'frontend_framework': '',
                'backend_framework': '',
                'package_manager': '',
                'web_server': '',
                'web_server_os': '',
                'languages': '',
                'date_created': '',
                'notes': ''
            }
            
            # Get basic project info
            result['date_created'] = full_project.created_at.split('T')[0] if full_project and full_project.created_at else ''
            
            # Repository size removed for performance (was heavy API call)
            
            # Get languages
            try:
                if full_project:
                    self._rate_limit_wait()
                    lang_start_time = time.time()
                    languages = self._api_call_with_retry(
                        lambda: full_project.languages()
                    )
                    lang_time = time.time() - lang_start_time
                    
                    if self.debug:
                        click.echo(f"Repository '{project.name}': Languages API call took {lang_time:.3f}s")
                    
                    if languages:
                        lang_list = [f"{lang}: {count}%" for lang, count in sorted(languages.items(), key=lambda x: x[1], reverse=True)]
                        result['languages'] = ', '.join(lang_list)
            except Exception:
                pass
            
            # Commit analysis removed for performance (was heavy API call)
            
            # Analyze for web app characteristics using cached project object
            analysis_start_time = time.time()
            web_analysis = self._analyze_web_app_type(full_project)
            analysis_time = time.time() - analysis_start_time
            result.update(web_analysis)
            
            repo_total_time = time.time() - repo_start_time
            
            if self.debug:
                click.echo(f"Repository '{project.name}': Web analysis took {analysis_time:.3f}s")
                click.echo(f"Repository '{project.name}': Total time {repo_total_time:.3f}s")
            
            return result
            
        except Exception as e:
            return {
                'name': project.name if hasattr(project, 'name') else 'Unknown',
                'url': project.web_url if hasattr(project, 'web_url') else '',
                'is_web_app': 'ERROR',
                'confidence': 'LOW',
                'web_app_type': '',
                'frontend_framework': '',
                'backend_framework': '',
                'package_manager': '',
                'web_server': '',
                'web_server_os': '',
                'languages': '',
                'date_created': '',
                'notes': f'Analysis error: {str(e)}'
            }
    
    def _analyze_web_app_type(self, project_obj: Any) -> Dict[str, Any]:
        """Analyze repository to determine if it's a web app and what type"""
        analysis = {
            'is_web_app': 'NO',
            'confidence': 'LOW',
            'web_app_type': '',
            'frontend_framework': '',
            'backend_framework': '',
            'package_manager': '',
            'web_server': '',
            'web_server_os': '',
            'notes': ''
        }
        
        evidence = []
        confidence_score = 0
        
        # Efficiently find relevant web app files using targeted search
        file_names = self._find_relevant_files(project_obj)
        
        # Priority 1: Check most common web app indicators first
        
        # Check for Node.js (package.json - very common)
        package_json_files = [f for f in file_names if f.endswith('package.json')]
        for package_json_path in package_json_files:
            package_json = self.get_file_content(project_obj, package_json_path)
            if package_json:
                try:
                    pkg_data = json.loads(package_json)
                    deps = {**pkg_data.get('dependencies', {}), **pkg_data.get('devDependencies', {})}
                    
                    # Check for backend Node.js frameworks
                    node_frameworks = {
                        'express': 'Express',
                        'fastify': 'Fastify', 
                        'koa': 'Koa',
                        '@nestjs/core': 'NestJS',
                        'next': 'Next.js'
                    }
                    
                    for dep, framework in node_frameworks.items():
                        if dep in deps:
                            analysis['is_web_app'] = 'YES'
                            analysis['web_app_type'] = 'Node.js'
                            analysis['backend_framework'] = framework
                            analysis['package_manager'] = 'npm'
                            confidence_score += 30
                            evidence.append(f'Found {framework} in package.json')
                            analysis['confidence'] = 'HIGH'
                            analysis['notes'] = '; '.join(evidence)
                            return analysis
                            
                except json.JSONDecodeError:
                    pass
            
        
        # Check for Python web frameworks (only if files exist)
        if 'requirements.txt' in file_names:
            requirements_txt = self.get_file_content(project_obj, self._get_file_path('requirements.txt'))
            if requirements_txt:
                python_frameworks = {
                    'django': 'Django',
                    'flask': 'Flask',
                    'fastapi': 'FastAPI',
                    'pyramid': 'Pyramid',
                    'tornado': 'Tornado'
                }
                
                for framework, name in python_frameworks.items():
                    if framework.lower() in requirements_txt.lower():
                        analysis['is_web_app'] = 'YES'
                        analysis['web_app_type'] = 'Python'
                        analysis['backend_framework'] = name
                        analysis['package_manager'] = 'pip'
                        confidence_score += 30
                        evidence.append(f'Found {name} in requirements.txt')
                        break  # Found framework, stop checking
        
        # Universal early termination for high confidence detections
        if confidence_score >= 30:
            analysis['confidence'] = 'HIGH'
            analysis['notes'] = '; '.join(evidence)
            return analysis
        
        # Priority 2: Check Java/Maven (pom.xml - very reliable)
        pom_xml_files = [f for f in file_names if f.endswith('pom.xml')]
        for pom_xml_path in pom_xml_files:
            pom_xml = self.get_file_content(project_obj, pom_xml_path)
            if pom_xml:
                # Priority-based Java web framework detection
                framework_detected = None
                
                # 1. Spring WebFlux (most specific)
                if 'spring-boot-starter-webflux' in pom_xml or 'spring-webflux' in pom_xml:
                    framework_detected = 'Spring WebFlux'
                    evidence.append('Found Spring WebFlux in pom.xml')
                
                # 2. Quarkus (very specific)
                elif ('quarkus-resteasy' in pom_xml or 'quarkus-resteasy-reactive' in pom_xml or 
                      'quarkus-maven-plugin' in pom_xml or 'quarkus-universe-bom' in pom_xml):
                    framework_detected = 'Quarkus'
                    evidence.append('Found Quarkus in pom.xml')
                
                # 3. JAX-RS/Jersey
                elif (any(pattern in pom_xml for pattern in [
                    'jersey-server', 'jersey-container-servlet', 'jersey-container-grizzly2-http',
                    'javax.ws.rs-api', 'org.glassfish.jersey', 'jersey-core'
                ])):
                    framework_detected = 'JAX-RS/Jersey'
                    evidence.append('Found JAX-RS/Jersey in pom.xml')
                
                # 4. Spring Boot (most common)
                elif 'spring-boot-starter-web' in pom_xml:
                    framework_detected = 'Spring Boot'
                    evidence.append('Found Spring Boot starter-web in pom.xml')
                
                # 5. Spring Boot (parent-based detection)
                elif 'spring-boot-starter-parent' in pom_xml and any(starter in pom_xml for starter in [
                    'spring-boot-starter', 'spring-web', 'spring-webmvc'
                ]):
                    framework_detected = 'Spring Boot'
                    evidence.append('Found Spring Boot parent with web dependencies in pom.xml')
                
                # 6. Spring Boot (enhanced detection for multi-module projects)
                elif 'spring-boot-starter-parent' in pom_xml and ('spring-boot-starter-web' in pom_xml):
                    framework_detected = 'Spring Boot'
                    evidence.append('Found Spring Boot parent with starter-web in pom.xml')
                
                # 6. Spring MVC (classic, not Spring Boot)
                elif 'spring-webmvc' in pom_xml and 'spring-boot' not in pom_xml:
                    framework_detected = 'Spring MVC'
                    evidence.append('Found Spring MVC in pom.xml')
                
                # 7. Generic Spring web detection
                elif 'springframework' in pom_xml and any(web_indicator in pom_xml for web_indicator in [
                    'servlet-api', 'spring-web', 'DispatcherServlet'
                ]):
                    framework_detected = 'Spring'
                    evidence.append('Found Spring web framework in pom.xml')
                
                # If any Java web framework detected
                if framework_detected:
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = 'Java'
                    analysis['backend_framework'] = framework_detected
                    analysis['package_manager'] = 'Maven'
                    confidence_score += 30
                    evidence.append(f'Found {framework_detected} in pom.xml')
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis  # Early termination
        
        # Priority 3: Check Go (go.mod - very reliable)
        if 'go.mod' in file_names:
            go_mod = self.get_file_content(project_obj, self._get_file_path('go.mod'))
            if go_mod:
                go_frameworks = {
                    'gin-gonic/gin': 'Gin',
                    'labstack/echo': 'Echo',
                    'gofiber/fiber': 'Fiber',
                    'gorilla/mux': 'Gorilla Mux',
                    'github.com/micro/go-micro': 'Go Micro',
                    'grpc-ecosystem/grpc-gateway': 'gRPC Gateway',
                    'google.golang.org/grpc': 'gRPC',
                    'golang.org/x/net': 'Go HTTP',
                    'github.com/aws/aws-lambda-go': 'AWS Lambda Go',
                    'aws/aws-lambda-go': 'AWS Lambda Go'
                }
                
                for framework, name in go_frameworks.items():
                    if framework in go_mod:
                        analysis['is_web_app'] = 'YES'
                        analysis['web_app_type'] = 'Go'
                        analysis['backend_framework'] = name
                        analysis['package_manager'] = 'Go Modules'
                        confidence_score += 30
                        evidence.append(f'Found {name} in go.mod')
                        analysis['confidence'] = 'HIGH'
                        analysis['notes'] = '; '.join(evidence)
                        return analysis
        
        # Priority 4: Check PHP composer (composer.json - very reliable)
        if 'composer.json' in file_names:
            composer_json = self.get_file_content(project_obj, self._get_file_path('composer.json'))
            if composer_json:
                try:
                    composer_data = json.loads(composer_json)
                    deps = composer_data.get('require', {})
                    
                    php_frameworks = {
                        'laravel/framework': 'Laravel',
                        'symfony/symfony': 'Symfony',
                        'symfony/framework-bundle': 'Symfony',
                        'codeigniter/framework': 'CodeIgniter',
                        'codeigniter4/framework': 'CodeIgniter 4'
                    }
                    
                    for dep, framework in php_frameworks.items():
                        if dep in deps:
                            analysis['is_web_app'] = 'YES'
                            analysis['web_app_type'] = 'PHP'
                            analysis['backend_framework'] = framework
                            analysis['package_manager'] = 'Composer'
                            confidence_score += 30
                            evidence.append(f'Found {framework} in composer.json')
                            analysis['confidence'] = 'HIGH'
                            analysis['notes'] = '; '.join(evidence)
                            return analysis
                except json.JSONDecodeError:
                    pass
        
        # Check for pyproject.toml (only if it exists and no backend found yet)
        if 'pyproject.toml' in file_names and not analysis['backend_framework']:
            pyproject_toml = self.get_file_content(project_obj, self._get_file_path('pyproject.toml'))
            if pyproject_toml:
                python_frameworks = ['django', 'flask', 'fastapi', 'pyramid', 'tornado']
                for framework in python_frameworks:
                    if framework in pyproject_toml.lower():
                        analysis['is_web_app'] = 'YES'
                        analysis['web_app_type'] = 'Python'
                        analysis['backend_framework'] = framework.title()
                        analysis['package_manager'] = 'pip'
                        confidence_score += 25
                        evidence.append(f'Found {framework} in pyproject.toml')
                        break
        
        # Check for Gradle (only if it exists and no backend found yet)
        if 'build.gradle' in file_names and not analysis['backend_framework']:
            build_gradle = self.get_file_content(project_obj, self._get_file_path('build.gradle'))
            if build_gradle:
                # Priority-based Java web framework detection for Gradle
                framework_detected = None
                
                # 1. Spring WebFlux
                if 'spring-boot-starter-webflux' in build_gradle or 'spring-webflux' in build_gradle:
                    framework_detected = 'Spring WebFlux'
                    evidence.append('Found Spring WebFlux in build.gradle')
                
                # 2. Quarkus
                elif ('quarkus-resteasy' in build_gradle or 'quarkus-gradle-plugin' in build_gradle or
                      'io.quarkus' in build_gradle):
                    framework_detected = 'Quarkus'
                    evidence.append('Found Quarkus in build.gradle')
                
                # 3. JAX-RS/Jersey
                elif (any(pattern in build_gradle for pattern in [
                    'jersey-server', 'jersey-container-servlet', 'javax.ws.rs-api', 
                    'org.glassfish.jersey', 'jersey-core'
                ])):
                    framework_detected = 'JAX-RS/Jersey'
                    evidence.append('Found JAX-RS/Jersey in build.gradle')
                
                # 4. Spring Boot
                elif 'spring-boot-starter-web' in build_gradle:
                    framework_detected = 'Spring Boot'
                    evidence.append('Found Spring Boot starter-web in build.gradle')
                
                # 5. Spring MVC
                elif 'spring-webmvc' in build_gradle and 'spring-boot' not in build_gradle:
                    framework_detected = 'Spring MVC'
                    evidence.append('Found Spring MVC in build.gradle')
                
                # If any Java web framework detected
                if framework_detected:
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = 'Java'
                    analysis['backend_framework'] = framework_detected
                    analysis['package_manager'] = 'Gradle'
                    confidence_score += 30
                    evidence.append(f'Found {framework_detected} in build.gradle')
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis  # Early termination
        
        # Check for .NET projects (use existing file list)
        csproj_files = [f for f in file_names if f.endswith('.csproj')]
        
        for csproj_file in csproj_files:
            csproj_content = self.get_file_content(project_obj, csproj_file)
            if csproj_content:
                # Priority 1: Check SDK attribute with enhanced Blazor detection
                if 'Sdk="Microsoft.NET.Sdk.Web"' in csproj_content:
                    # Check for Blazor WebAssembly packages first (most specific)
                    webassembly_packages = [
                        'Microsoft.AspNetCore.Components.WebAssembly',
                        'Microsoft.AspNetCore.Components.WebAssembly.Build',
                        'Microsoft.AspNetCore.Components.WebAssembly.Server',
                        'Microsoft.AspNetCore.Components.WebAssembly.Authentication',
                        'Microsoft.AspNetCore.Components.WebAssembly.DevServer'
                    ]
                    
                    for package in webassembly_packages:
                        if package in csproj_content:
                            analysis['is_web_app'] = 'YES'
                            analysis['web_app_type'] = '.NET Core'
                            analysis['backend_framework'] = 'Blazor WebAssembly'
                            analysis['package_manager'] = 'NuGet'
                            confidence_score += 35
                            evidence.append(f'Found {package} package')
                            analysis['confidence'] = 'HIGH'
                            analysis['notes'] = '; '.join(evidence)
                            return analysis  # Early termination
                    
                    # Check for Blazor Server package reference (Components without WebAssembly)
                    if ('Microsoft.AspNetCore.Components' in csproj_content and
                        'Microsoft.AspNetCore.Components.WebAssembly' not in csproj_content):
                        analysis['is_web_app'] = 'YES'
                        analysis['web_app_type'] = '.NET Core'
                        analysis['backend_framework'] = 'Blazor Server'
                        analysis['package_manager'] = 'NuGet'
                        confidence_score += 35
                        evidence.append('Found Blazor Server components in Web SDK')
                        analysis['confidence'] = 'HIGH'
                        analysis['notes'] = '; '.join(evidence)
                        return analysis  # Early termination
                    
                    # Enhanced check: Look for Blazor Server configuration in Startup.cs
                    startup_files = [f for f in file_names if f.endswith('Startup.cs')]
                    for startup_file in startup_files:
                        startup_content = self.get_file_content(project_obj, startup_file)
                        if startup_content and ('AddServerSideBlazor' in startup_content or 'MapBlazorHub' in startup_content):
                            analysis['is_web_app'] = 'YES'
                            analysis['web_app_type'] = '.NET Core'
                            analysis['backend_framework'] = 'Blazor Server'
                            analysis['package_manager'] = 'NuGet'
                            confidence_score += 35
                            evidence.append('Found Blazor Server configuration in Startup.cs')
                            analysis['confidence'] = 'HIGH'
                            analysis['notes'] = '; '.join(evidence)
                            return analysis  # Early termination
                    
                    # Enhanced check: Look for Blazor Server markup in _Host.cshtml
                    host_files = [f for f in file_names if f.endswith('_Host.cshtml')]
                    for host_file in host_files:
                        host_content = self.get_file_content(project_obj, host_file)
                        if host_content and ('blazor.server.js' in host_content or 'ServerPrerendered' in host_content):
                            analysis['is_web_app'] = 'YES'
                            analysis['web_app_type'] = '.NET Core'
                            analysis['backend_framework'] = 'Blazor Server'
                            analysis['package_manager'] = 'NuGet'
                            confidence_score += 35
                            evidence.append('Found Blazor Server markup in _Host.cshtml')
                            analysis['confidence'] = 'HIGH'
                            analysis['notes'] = '; '.join(evidence)
                            return analysis  # Early termination
                    
                    # Default to ASP.NET Core if no Blazor patterns found
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Core'
                    analysis['backend_framework'] = 'ASP.NET Core'
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 35
                    evidence.append('Found Web SDK in .csproj')
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis  # Early termination
                
                # Priority 2: Check Blazor SDK attributes
                elif 'Sdk="Microsoft.NET.Sdk.BlazorWebAssembly"' in csproj_content:
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Core'
                    analysis['backend_framework'] = 'Blazor WebAssembly'
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 35
                    evidence.append('Found Blazor WebAssembly SDK in .csproj')
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis  # Early termination
                
                # Priority 2c: Enhanced Blazor WebAssembly detection
                # Check for WebAssembly-specific package patterns
                webassembly_packages = [
                    'Microsoft.AspNetCore.Components.WebAssembly',
                    'Microsoft.AspNetCore.Components.WebAssembly.Build',
                    'Microsoft.AspNetCore.Components.WebAssembly.Server',
                    'Microsoft.AspNetCore.Components.WebAssembly.Authentication',
                    'Microsoft.AspNetCore.Components.WebAssembly.DevServer'
                ]
                
                webassembly_found = False
                webassembly_evidence = ''
                for package in webassembly_packages:
                    if package in csproj_content:
                        webassembly_found = True
                        webassembly_evidence = f'Found {package} package'
                        break
                
                if webassembly_found:
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Core'
                    analysis['backend_framework'] = 'Blazor WebAssembly'
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 35
                    evidence.append(webassembly_evidence)
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis  # Early termination
                
                # Priority 3: Enhanced serverless .NET detection
                # Check for AWS Lambda-specific packages
                lambda_packages = [
                    'Amazon.Lambda.Core',
                    'Amazon.Lambda.APIGatewayEvents',
                    'Amazon.Lambda.RuntimeSupport',
                    'Amazon.Lambda.AspNetCore.Server.Hosting',
                    'Amazon.Lambda.Serialization.SystemTextJson'
                ]
                
                lambda_found = False
                lambda_evidence = ''
                for package in lambda_packages:
                    if package in csproj_content:
                        lambda_found = True
                        lambda_evidence = f'Found {package} package'
                        break
                
                # Check for AWS Lambda project type
                if not lambda_found and '<AWSProjectType>Lambda</AWSProjectType>' in csproj_content:
                    lambda_found = True
                    lambda_evidence = 'Found AWS Lambda project type'
                
                # Check for aws-lambda-tools-defaults.json
                if not lambda_found:
                    lambda_config_files = [f for f in file_names if f.endswith('aws-lambda-tools-defaults.json')]
                    if lambda_config_files:
                        lambda_found = True
                        lambda_evidence = 'Found AWS Lambda tools configuration'
                
                # Check for SAM template files
                if not lambda_found:
                    sam_files = [f for f in file_names if f.endswith('template.yaml') or f.endswith('template.yml')]
                    for sam_file in sam_files:
                        sam_content = self.get_file_content(project_obj, sam_file)
                        if sam_content and 'AWS::Serverless::Function' in sam_content:
                            lambda_found = True
                            lambda_evidence = 'Found AWS SAM template'
                            break
                
                if lambda_found:
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Core'
                    analysis['backend_framework'] = 'AWS Lambda .NET'
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 30
                    evidence.append(lambda_evidence)
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis  # Early termination
                
                # Check for Azure Functions
                elif ('Microsoft.Azure.Functions' in csproj_content or 
                      'Microsoft.NET.Sdk.Functions' in csproj_content):
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Core'
                    analysis['backend_framework'] = 'Azure Functions'
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 30
                    evidence.append('Found Azure Functions packages in .csproj')
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis  # Early termination
                
                # Priority 4: Check package references (already loaded content)
                elif 'Microsoft.AspNetCore' in csproj_content or 'AspNetCore' in csproj_content:
                    # Check for specific patterns to determine framework type
                    if 'Microsoft.AspNetCore.OpenApi' in csproj_content or 'Swashbuckle' in csproj_content:
                        framework_name = 'ASP.NET Core Web API'
                    elif 'Microsoft.AspNetCore.Mvc' in csproj_content:
                        framework_name = 'ASP.NET Core MVC'
                    else:
                        framework_name = 'ASP.NET Core'
                    
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Core'
                    analysis['backend_framework'] = framework_name
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 30
                    evidence.append(f'Found {framework_name} packages in .csproj')
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis  # Early termination
                
                # Priority 4: Check legacy .NET Framework
                elif 'System.Web' in csproj_content:
                    # Try to determine specific framework type
                    if 'System.Web.Mvc' in csproj_content:
                        framework_name = 'ASP.NET MVC'
                    elif 'System.Web.Http' in csproj_content:
                        framework_name = 'ASP.NET Web API'
                    else:
                        framework_name = 'ASP.NET'
                    
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Framework'
                    analysis['backend_framework'] = framework_name
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 30
                    evidence.append(f'Found {framework_name} in .csproj')
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis  # Early termination
        
        # Check for packages.config (legacy .NET Framework package management)
        packages_config_files = [f for f in file_names if f.endswith('packages.config')]
        if packages_config_files and not analysis['backend_framework']:
            for packages_config_path in packages_config_files:
                packages_config = self.get_file_content(project_obj, packages_config_path)
                if packages_config:
                    # Enhanced check for legacy ASP.NET MVC with version detection
                    if 'Microsoft.AspNet.Mvc' in packages_config:
                        # Check for MVC 5.x pattern
                        if 'version="5.' in packages_config:
                            framework_name = 'ASP.NET MVC 5'
                            evidence_text = 'Found ASP.NET MVC 5.x in packages.config'
                        else:
                            framework_name = 'ASP.NET MVC'
                            evidence_text = 'Found ASP.NET MVC in packages.config'
                        
                        analysis['is_web_app'] = 'YES'
                        analysis['web_app_type'] = '.NET Framework'
                        analysis['backend_framework'] = framework_name
                        analysis['package_manager'] = 'NuGet'
                        confidence_score += 30
                        evidence.append(evidence_text)
                        analysis['confidence'] = 'HIGH'
                        analysis['notes'] = '; '.join(evidence)
                        return analysis  # Early termination
                    
                    # Check for legacy ASP.NET Web API
                    elif 'Microsoft.AspNet.WebApi' in packages_config:
                        analysis['is_web_app'] = 'YES'
                        analysis['web_app_type'] = '.NET Framework'
                        analysis['backend_framework'] = 'ASP.NET Web API'
                        analysis['package_manager'] = 'NuGet'
                        confidence_score += 30
                        evidence.append('Found ASP.NET Web API in packages.config')
                        analysis['confidence'] = 'HIGH'
                        analysis['notes'] = '; '.join(evidence)
                        return analysis  # Early termination
                    
                    # Check for generic ASP.NET
                    elif 'Microsoft.AspNet' in packages_config:
                        analysis['is_web_app'] = 'YES'
                        analysis['web_app_type'] = '.NET Framework'
                        analysis['backend_framework'] = 'ASP.NET'
                        analysis['package_manager'] = 'NuGet'
                        confidence_score += 25
                        evidence.append('Found ASP.NET in packages.config')
                        analysis['confidence'] = 'MEDIUM'
                        analysis['notes'] = '; '.join(evidence)
                        return analysis  # Early termination
        
        # Enhanced .NET Solution file check (only if no .csproj detection)
        if not analysis['backend_framework']:
            sln_files = [f for f in file_names if f.endswith('.sln')]
            
            for sln_file in sln_files:
                sln_content = self.get_file_content(project_obj, sln_file)
                if sln_content:
                    # Parse solution file to extract .csproj paths
                    csproj_paths = self._parse_solution_file(sln_content, sln_file)
                    
                    # Analyze each .csproj file found in the solution
                    for csproj_path in csproj_paths:
                        csproj_content = self.get_file_content(project_obj, csproj_path)
                        if csproj_content:
                            # Run the same .csproj analysis logic as above
                            result = self._analyze_csproj_content(csproj_content, csproj_path, project_obj, file_names, evidence, confidence_score)
                            if result:
                                return result
                    
                    # Fallback to simple string matching for web indicators if no .csproj found
                    web_indicators = [
                        '.Web', '.WebApi', '.Mvc', 'Microsoft.AspNetCore', 
                        'AspNet', 'System.Web', 'Web.csproj'
                    ]
                    
                    if any(indicator in sln_content for indicator in web_indicators):
                        analysis['is_web_app'] = 'YES'
                        analysis['package_manager'] = 'NuGet'
                        confidence_score += 25
                        evidence.append(f'Found web indicators in {sln_file}')
                        
                        # Determine .NET type from solution content
                        if 'Microsoft.AspNetCore' in sln_content or 'netcore' in sln_content.lower():
                            analysis['web_app_type'] = '.NET Core'
                            analysis['backend_framework'] = 'ASP.NET Core'
                        else:
                            analysis['web_app_type'] = '.NET Framework'
                            analysis['backend_framework'] = 'ASP.NET'
                        
                        analysis['confidence'] = 'MEDIUM'
                        analysis['notes'] = '; '.join(evidence)
                        return analysis  # Early termination
        
        # Check for web.config (ASP.NET) (only if it exists and no backend found yet)
        web_config_files = [f for f in file_names if f.endswith('web.config')]
        if web_config_files and not analysis['backend_framework']:
            analysis['is_web_app'] = 'YES'
            analysis['web_app_type'] = '.NET Framework'
            analysis['backend_framework'] = 'ASP.NET'
            analysis['web_server_os'] = 'Windows'
            analysis['package_manager'] = 'NuGet'
            confidence_score += 25
            evidence.append(f'Found {web_config_files[0]} file')
            analysis['confidence'] = 'MEDIUM'
            analysis['notes'] = '; '.join(evidence)
            return analysis  # Early termination
        
        # Check for Global.asax (ASP.NET) (only if it exists and no backend found yet)
        global_asax_files = [f for f in file_names if f.endswith('Global.asax') or f.endswith('Global.asax.cs')]
        if global_asax_files and not analysis['backend_framework']:
            analysis['is_web_app'] = 'YES'
            analysis['web_app_type'] = '.NET Framework'
            analysis['backend_framework'] = 'ASP.NET'
            analysis['web_server_os'] = 'Windows'
            analysis['package_manager'] = 'NuGet'
            confidence_score += 25
            evidence.append(f'Found {global_asax_files[0]} file')
            analysis['confidence'] = 'MEDIUM'
            analysis['notes'] = '; '.join(evidence)
            return analysis  # Early termination
        
        # Priority 6: Check for remaining lower-confidence indicators
        
        # Check for main.go (only if it exists and no backend found yet)
        main_go_files = [f for f in file_names if f.endswith('main.go')]
        if main_go_files and not analysis['backend_framework']:
            for main_go_path in main_go_files:
                main_go = self.get_file_content(project_obj, main_go_path)
                if main_go:
                    # Check for various Go web/service patterns
                    if 'http.ListenAndServe' in main_go:
                        framework = 'Go HTTP'
                    elif 'gin.Default' in main_go:
                        framework = 'Gin'
                    elif 'micro.NewService' in main_go:
                        framework = 'Go Micro'
                    elif 'lambda.Start' in main_go:
                        framework = 'AWS Lambda Go'
                    elif 'echo.New' in main_go:
                        framework = 'Echo'
                    elif 'fiber.New' in main_go:
                        framework = 'Fiber'
                    else:
                        framework = None
                    
                    if framework:
                        analysis['is_web_app'] = 'YES'
                        analysis['web_app_type'] = 'Go'
                        analysis['backend_framework'] = framework
                        confidence_score += 25
                        evidence.append(f'Found {framework} in {main_go_path}')
                        break
        
        # Check for index.php (only if it exists and no backend found yet)
        if 'index.php' in file_names and not analysis['backend_framework']:
            index_php = self.get_file_content(project_obj, 'index.php')
            if index_php:
                analysis['is_web_app'] = 'YES'
                analysis['web_app_type'] = 'PHP'
                analysis['backend_framework'] = 'PHP'
                confidence_score += 20
                evidence.append('Found index.php file')
        
        # Check for serverless functions (only if files exist)
        if 'serverless.yml' in file_names:
            serverless_yml = self.get_file_content(project_obj, 'serverless.yml')
            if serverless_yml:
                analysis['is_web_app'] = 'YES'
                analysis['web_app_type'] = 'AWS Lambda'
                confidence_score += 30
                evidence.append('Found serverless.yml')
        
        if 'host.json' in file_names:
            host_json = self.get_file_content(project_obj, 'host.json')
            if host_json:
                analysis['is_web_app'] = 'YES'
                analysis['web_app_type'] = 'Azure Functions'
                confidence_score += 30
                evidence.append('Found host.json (Azure Functions)')
        
        
        # Set confidence level
        if confidence_score >= 30:
            analysis['confidence'] = 'HIGH'
        elif confidence_score >= 15:
            analysis['confidence'] = 'MEDIUM'
        else:
            analysis['confidence'] = 'LOW'
        
        # If we found evidence but no clear framework, mark as potential web app
        if evidence and analysis['is_web_app'] == 'NO':
            analysis['is_web_app'] = 'UNKNOWN'
        
        analysis['notes'] = '; '.join(evidence) if evidence else 'No web app indicators found'
        
        return analysis

    def _parse_solution_file(self, sln_content: str, sln_file: str) -> List[str]:
        """Parse .sln file to extract .csproj file paths"""
        import re
        import os
        
        csproj_paths = []
        
        # Parse Visual Studio solution file format
        # Look for Project entries like: Project("{...}") = "ProjectName", "path\to\project.csproj", "{...}"
        project_pattern = r'Project\("[^"]*"\)\s*=\s*"[^"]*",\s*"([^"]*\.csproj)"'
        matches = re.findall(project_pattern, sln_content)
        
        for match in matches:
            # Convert Windows path separators to Unix
            csproj_path = match.replace('\\', '/')
            
            # Make path relative to solution file location
            sln_dir = os.path.dirname(sln_file)
            if sln_dir:
                full_path = f"{sln_dir}/{csproj_path}"
            else:
                full_path = csproj_path
            
            csproj_paths.append(full_path)
        
        return csproj_paths

    def _analyze_csproj_content(self, csproj_content: str, csproj_path: str, project_obj: Any, file_names: List[str], evidence: List[str], confidence_score: int) -> Optional[Dict[str, Any]]:
        """Analyze .csproj content and return analysis result if it's a web app"""
        analysis = {
            'is_web_app': 'NO',
            'confidence': 'LOW',
            'web_app_type': '',
            'frontend_framework': '',
            'backend_framework': '',
            'package_manager': '',
            'web_server': '',
            'web_server_os': '',
            'notes': ''
        }
        
        # Priority 1: Check SDK attribute with enhanced Blazor detection
        if 'Sdk="Microsoft.NET.Sdk.Web"' in csproj_content:
            # Check for Blazor WebAssembly packages first (most specific)
            webassembly_packages = [
                'Microsoft.AspNetCore.Components.WebAssembly',
                'Microsoft.AspNetCore.Components.WebAssembly.Build',
                'Microsoft.AspNetCore.Components.WebAssembly.Server',
                'Microsoft.AspNetCore.Components.WebAssembly.Authentication',
                'Microsoft.AspNetCore.Components.WebAssembly.DevServer'
            ]
            
            for package in webassembly_packages:
                if package in csproj_content:
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Core'
                    analysis['backend_framework'] = 'Blazor WebAssembly'
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 35
                    evidence.append(f'Found {package} package in {csproj_path}')
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis
            
            # Check for Blazor Server package reference (Components without WebAssembly)
            if ('Microsoft.AspNetCore.Components' in csproj_content and
                'Microsoft.AspNetCore.Components.WebAssembly' not in csproj_content):
                analysis['is_web_app'] = 'YES'
                analysis['web_app_type'] = '.NET Core'
                analysis['backend_framework'] = 'Blazor Server'
                analysis['package_manager'] = 'NuGet'
                confidence_score += 35
                evidence.append(f'Found Blazor Server components in {csproj_path}')
                analysis['confidence'] = 'HIGH'
                analysis['notes'] = '; '.join(evidence)
                return analysis
            
            # Enhanced check: Look for Blazor Server configuration in Startup.cs
            startup_files = [f for f in file_names if f.endswith('Startup.cs')]
            for startup_file in startup_files:
                startup_content = self.get_file_content(project_obj, startup_file)
                if startup_content and ('AddServerSideBlazor' in startup_content or 'MapBlazorHub' in startup_content):
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Core'
                    analysis['backend_framework'] = 'Blazor Server'
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 35
                    evidence.append(f'Found Blazor Server configuration in Startup.cs (from {csproj_path})')
                    analysis['confidence'] = 'HIGH'
                    analysis['notes'] = '; '.join(evidence)
                    return analysis
            
            # Default to ASP.NET Core if no Blazor patterns found
            analysis['is_web_app'] = 'YES'
            analysis['web_app_type'] = '.NET Core'
            analysis['backend_framework'] = 'ASP.NET Core'
            analysis['package_manager'] = 'NuGet'
            confidence_score += 35
            evidence.append(f'Found Web SDK in {csproj_path}')
            analysis['confidence'] = 'HIGH'
            analysis['notes'] = '; '.join(evidence)
            return analysis
        
        # Priority 2: Check Blazor SDK attributes
        elif 'Sdk="Microsoft.NET.Sdk.BlazorWebAssembly"' in csproj_content:
            analysis['is_web_app'] = 'YES'
            analysis['web_app_type'] = '.NET Core'
            analysis['backend_framework'] = 'Blazor WebAssembly'
            analysis['package_manager'] = 'NuGet'
            confidence_score += 35
            evidence.append(f'Found Blazor WebAssembly SDK in {csproj_path}')
            analysis['confidence'] = 'HIGH'
            analysis['notes'] = '; '.join(evidence)
            return analysis
        
        # Priority 3: Check for ASP.NET Core package references
        elif 'Microsoft.AspNetCore' in csproj_content or 'AspNetCore' in csproj_content:
            # Check for specific patterns to determine framework type
            if 'Microsoft.AspNetCore.OpenApi' in csproj_content or 'Swashbuckle' in csproj_content:
                framework_name = 'ASP.NET Core Web API'
            elif 'Microsoft.AspNetCore.Mvc' in csproj_content:
                framework_name = 'ASP.NET Core MVC'
            else:
                framework_name = 'ASP.NET Core'
            
            analysis['is_web_app'] = 'YES'
            analysis['web_app_type'] = '.NET Core'
            analysis['backend_framework'] = framework_name
            analysis['package_manager'] = 'NuGet'
            confidence_score += 30
            evidence.append(f'Found {framework_name} packages in {csproj_path}')
            analysis['confidence'] = 'HIGH'
            analysis['notes'] = '; '.join(evidence)
            return analysis
        
        # Priority 4: Check for legacy .NET Framework web patterns
        elif 'System.Web.Mvc' in csproj_content:
            analysis['is_web_app'] = 'YES'
            analysis['web_app_type'] = '.NET Framework'
            analysis['backend_framework'] = 'ASP.NET MVC'
            analysis['package_manager'] = 'NuGet'
            confidence_score += 30
            evidence.append(f'Found ASP.NET MVC in {csproj_path}')
            analysis['confidence'] = 'HIGH'
            analysis['notes'] = '; '.join(evidence)
            return analysis
        
        elif 'System.Web.Http' in csproj_content:
            analysis['is_web_app'] = 'YES'
            analysis['web_app_type'] = '.NET Framework'
            analysis['backend_framework'] = 'ASP.NET Web API'
            analysis['package_manager'] = 'NuGet'
            confidence_score += 30
            evidence.append(f'Found ASP.NET Web API in {csproj_path}')
            analysis['confidence'] = 'HIGH'
            analysis['notes'] = '; '.join(evidence)
            return analysis
        
        elif 'System.Web' in csproj_content:
            analysis['is_web_app'] = 'YES'
            analysis['web_app_type'] = '.NET Framework'
            analysis['backend_framework'] = 'ASP.NET'
            analysis['package_manager'] = 'NuGet'
            confidence_score += 25
            evidence.append(f'Found ASP.NET in {csproj_path}')
            analysis['confidence'] = 'MEDIUM'
            analysis['notes'] = '; '.join(evidence)
            return analysis
        
        # If no web patterns found, return None
        return None


@click.command()
@click.option('--gitlab-url', help='GitLab instance URL')
@click.option('--token', help='Personal access token')
@click.option('--output', help='Output CSV filename')
@click.option('--filter', 'name_filter', default=None, help='Repository name filter (default: all repositories)')
@click.option('--rate-limit', default=20.0, help='Requests per second (default: 20)')
@click.option('--debug', is_flag=True, help='Enable debug logging for performance analysis')
@click.option('--no-rate-limit', is_flag=True, help='Disable rate limiting (for testing)')
@click.option('--search-depth', default=2, help='Maximum directory depth to search (default: 2)')
def main(gitlab_url, token, output, name_filter, rate_limit, debug, no_rate_limit, search_depth):
    """GitLab Web App Repository Analyzer"""
    
    # Generate default output filename if not provided
    if not output:
        timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
        output = f'gitlab-analysis-{timestamp}.csv'
    
    # Get GitLab URL from environment if not provided
    if not gitlab_url:
        gitlab_url = os.getenv('GITLAB_URL')
        if not gitlab_url:
            raise click.ClickException("GitLab URL must be provided via --gitlab-url or GITLAB_URL environment variable")
    
    # Get token from environment if not provided
    if not token:
        token = os.getenv('GITLAB_TOKEN')
    
    click.echo(f"Starting GitLab analysis...")
    click.echo(f"GitLab URL: {gitlab_url}")
    click.echo(f"Output file: {output}")
    click.echo(f"Rate limit: {rate_limit} requests/second")
    
    try:
        # Initialize analyzer
        analyzer = GitLabAnalyzer(gitlab_url, token, rate_limit, debug, search_depth)
        
        # Set no_rate_limit flag for testing
        if no_rate_limit:
            analyzer.no_rate_limit = True
            click.echo("Rate limiting disabled for testing")
        
        # Get repositories
        click.echo("Fetching repositories...")
        repositories = analyzer.get_repositories(name_filter)
        click.echo(f"Found {len(repositories)} repositories to analyze")
        
        # Analyze repositories
        results = []
        analysis_start_time = time.time()
        
        with click.progressbar(repositories, label='Analyzing repositories') as repos:
            for repo in repos:
                result = analyzer.analyze_repository(repo)
                results.append(result)
        
        analysis_total_time = time.time() - analysis_start_time
        
        # Write CSV output
        click.echo(f"Writing results to {output}...")
        csv_columns = [
            'Repository Name', 'Repository URL', 'Is Web App', 'Confidence Level',
            'Web App Type', 'Frontend Framework', 'Backend Framework', 'Package Manager',
            'Web Server', 'Web Server OS', 'Languages', 'Date Created', 'Notes'
        ]
        
        with open(output, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            
            for result in results:
                writer.writerow({
                    'Repository Name': result['name'],
                    'Repository URL': result['url'],
                    'Is Web App': result['is_web_app'],
                    'Confidence Level': result['confidence'],
                    'Web App Type': result['web_app_type'],
                    'Frontend Framework': result['frontend_framework'],
                    'Backend Framework': result['backend_framework'],
                    'Package Manager': result['package_manager'],
                    'Web Server': result['web_server'],
                    'Web Server OS': result['web_server_os'],
                    'Languages': result['languages'],
                    'Date Created': result['date_created'],
                    'Notes': result['notes']
                })
        
        # Summary
        web_apps = len([r for r in results if r['is_web_app'] == 'YES'])
        errors = len([r for r in results if r['is_web_app'] == 'ERROR'])
        
        click.echo(f"\nAnalysis complete!")
        click.echo(f"Total repositories analyzed: {len(results)}")
        click.echo(f"Web applications found: {web_apps}")
        click.echo(f"Errors encountered: {errors}")
        click.echo(f"Results saved to: {output}")
        
        # Performance summary
        if debug:
            click.echo(f"\nPerformance Debug Summary:")
            click.echo(f"Total API calls: {analyzer.api_call_count}")
            click.echo(f"Total rate limit wait time: {analyzer.total_wait_time:.1f}s")
            click.echo(f"Analysis time: {analysis_total_time:.1f}s")
            click.echo(f"Rate limit overhead: {(analyzer.total_wait_time/analysis_total_time)*100:.1f}%")
            click.echo(f"Average per repo: {analysis_total_time/len(results):.2f}s")
            click.echo(f"Expected rate limit interval: {1.0/rate_limit:.3f}s")
        
    except Exception as e:
        raise click.ClickException(f"Analysis failed: {e}")


if __name__ == '__main__':
    main()  # type: ignore