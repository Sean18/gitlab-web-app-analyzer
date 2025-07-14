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

# Import performance tracking module
from performance_tracker import create_performance_tracker


class GitLabAnalyzer:
    """Main analyzer class for GitLab repositories"""
    
    def __init__(self, gitlab_url: str, token: Optional[str] = None, rate_limit: float = 2.0, debug: bool = False, max_search_depth: int = 2, enable_performance_tracking: bool = False):
        self.gitlab_url = gitlab_url
        self.rate_limit = rate_limit
        self.last_request_time = 0
        self.debug = debug
        self.api_call_count = 0
        self.total_wait_time = 0
        self.no_rate_limit = False
        self.max_search_depth = max_search_depth  # Maximum directory depth to search
        self.performance_tracker = create_performance_tracker(enable_performance_tracking)
        
        # Directory tracking for progressive level search optimization
        self.current_level_dirs = []  # Directories to search at current level
        self.next_level_dirs = []     # Directories discovered for next level
        
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
    
    def _api_call_with_retry(self, api_call, max_retries=3, call_type='other'):
        """Execute API call with retry logic for rate limit errors and performance tracking"""
        with self.performance_tracker.track_api_call_context(call_type, self.debug):
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
                lambda: self.gl.projects.list(membership=True, per_page=100),
                call_type='project_list'
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
                    lambda: project_obj.files.get(file_path, ref=branch_name),
                    call_type='file_content'
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
    
    def _find_relevant_files_at_level(self, project_obj: Any, level: int) -> List[str]:
        """Get files at specific directory level using optimized progressive search"""
        """Performance Note:  We do this because getting the full tree (recursive) is too slow."""
        found_files = []
        
        # Use the current level directories (no more rebuilding from scratch)
        directories_to_search = self.current_level_dirs
        
        # Search the directories at the current level
        for dir_path in directories_to_search:
            self._rate_limit_wait()
            
            try:
                query_params: Dict[str, Any] = {'recursive': False}
                if dir_path:
                    query_params['path'] = dir_path
                
                with self.performance_tracker.track_api_call_context('file_tree', self.debug):
                    items = self.gl.http_list(
                        f'/projects/{project_obj.id}/repository/tree',
                        query_data=query_params,
                        get_all=True
                    )
                
                for item in items:
                    if item['type'] == 'blob':  # File
                        file_name = item['name']
                        if self._is_target_file(file_name):
                            found_files.append(item['path'])
                    elif item['type'] == 'tree':  # Directory
                        # Store directories for next level search
                        self.next_level_dirs.append(item['path'])
                            
            except Exception as e:
                if self.debug:
                    click.echo(f"Debug: Error accessing directory '{dir_path}': {e}")
                continue
        
        return found_files
    
    def analyze_repository(self, project: Any) -> Dict[str, Any]:
        """Analyze a single repository for web app characteristics"""
        with self.performance_tracker.track_repository(project.name) as repo_tracker:
            try:
                self._rate_limit_wait()
                full_project = self._api_call_with_retry(
                    lambda: self.gl.projects.get(project.id),
                    call_type='project_info'
                )
                
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
                
                # Get languages
                try:
                    if full_project:
                        self._rate_limit_wait()
                        languages = self._api_call_with_retry(
                            lambda: full_project.languages(),
                            call_type='languages'
                        )
                        
                        if languages:
                            lang_list = [f"{lang}: {count}%" for lang, count in sorted(languages.items(), key=lambda x: x[1], reverse=True)]
                            result['languages'] = ', '.join(lang_list)
                except Exception:
                    pass
                
                # Analyze for web app characteristics using cached project object
                web_analysis = self._analyze_web_app_type(full_project)
                result.update(web_analysis)
                
                # Finish performance tracking for this repository
                app_type = result.get('web_app_type', 'Unknown')
                if result.get('is_web_app') == 'NO':
                    app_type = 'Non-Web-App'
                elif result.get('is_web_app') == 'ERROR':
                    app_type = 'Error'
                detection_level = result.get('detection_level', -1)
                repo_tracker.finish(app_type, detection_level)
                
                return result
                
            except Exception as e:
                repo_tracker.finish('Error', -1)
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
        """Analyze repository to determine if it's a web app and what type using progressive depth search"""
        # Progressive depth search: analyze files Directory level by level
        max_depth = self.max_search_depth
        
        # Initialize directory tracking for progressive search optimization
        self.current_level_dirs = [""]  # Start with root directory
        self.next_level_dirs = []
        
        all_files = []  # Accumulate files across levels
        
        for level in range(max_depth + 1):
            # Get files at current level only
            level_files = self._find_relevant_files_at_level(project_obj, level)
            
            # Update directory lists for next level
            self.current_level_dirs = self.next_level_dirs
            self.next_level_dirs = []
            
            if self.debug:
                click.echo(f"Debug: Level {level} found {len(level_files)} relevant files")
            
            if not level_files:
                continue  # No relevant files at this level, try next level
            
            # Add new files to our collection
            all_files.extend(level_files)
            
            # Analyze all files we have so far (this reuses existing analysis logic)
            analysis = self._analyze_files_for_web_app_complete(all_files, project_obj)
            
            # If we get high confidence, stop here
            if analysis['confidence'] == 'HIGH':
                analysis['detection_level'] = level
                if self.debug:
                    click.echo(f"Debug: HIGH confidence detection at level {level}")
                return analysis
        
        # If we get here, analyze with all files we found
        if all_files:
            analysis = self._analyze_files_for_web_app_complete(all_files, project_obj)
            # Set detection level to max depth if not already set
            if 'detection_level' not in analysis:
                analysis['detection_level'] = max_depth
            return analysis
        else:
            # No files found at any level
            return {
                'is_web_app': 'NO',
                'confidence': 'LOW',
                'web_app_type': '',
                'frontend_framework': '',
                'backend_framework': '',
                'package_manager': '',
                'web_server': '',
                'web_server_os': '',
                'notes': 'No relevant files found',
                'detection_level': -1
            }
    
    def _analyze_files_for_web_app_complete(self, file_names: List[str], project_obj: Any) -> Dict[str, Any]:
        """Analyze a set of files for web app characteristics - contains full analysis logic"""
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
        
        # Priority 1: Check most common web app indicators first
        
        # Check for Node.js (package.json - very common)
        package_json_files = [f for f in file_names if f.endswith('package.json')]
        for package_json_filename in package_json_files:
            package_json = self.get_file_content(project_obj, package_json_filename)
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
        requirements_files = [f for f in file_names if f.endswith('requirements.txt')]
        if requirements_files:
            for requirements_file in requirements_files:
                requirements_txt = self.get_file_content(project_obj, requirements_file)
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
                            analysis['confidence'] = 'HIGH'
                            analysis['notes'] = '; '.join(evidence)
                            return analysis
        
        # Universal early termination for high confidence detections
        if confidence_score >= 30:
            analysis['confidence'] = 'HIGH'
            analysis['notes'] = '; '.join(evidence)
            return analysis
        
        # Priority 2: Check Java/Maven (pom.xml - very reliable)
        pom_xml_files = [f for f in file_names if f.endswith('pom.xml')]
        for pom_xml_filename in pom_xml_files:
            pom_xml = self.get_file_content(project_obj, pom_xml_filename)
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
        go_mod_files = [f for f in file_names if f.endswith('go.mod')]
        if go_mod_files:
            for go_mod_file in go_mod_files:
                go_mod = self.get_file_content(project_obj, go_mod_file)
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
        composer_files = [f for f in file_names if f.endswith('composer.json')]
        if composer_files:
            for composer_file in composer_files:
                composer_json = self.get_file_content(project_obj, composer_file)
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
        pyproject_files = [f for f in file_names if f.endswith('pyproject.toml')]
        if pyproject_files and not analysis['backend_framework']:
            for pyproject_file in pyproject_files:
                pyproject_toml = self.get_file_content(project_obj, pyproject_file)
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
            build_gradle = self.get_file_content(project_obj, 'build.gradle')
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
                result = self._analyze_csproj_content(csproj_content, csproj_file, project_obj, file_names, evidence, confidence_score)
                if result:
                    return result
        
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
            for main_go_filename in main_go_files:
                main_go = self.get_file_content(project_obj, main_go_filename)
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
                        analysis['package_manager'] = 'Go'
                        confidence_score += 25
                        evidence.append(f'Found {framework} in {main_go_filename}')
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
@click.option('--max-depth', default=2, help='Maximum directory depth to search (default: 2)')
def main(gitlab_url, token, output, name_filter, rate_limit, debug, no_rate_limit, max_depth):
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
        # Initialize analyzer (performance tracking disabled by default)
        analyzer = GitLabAnalyzer(gitlab_url, token, rate_limit, debug, max_depth, enable_performance_tracking=False)
        
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