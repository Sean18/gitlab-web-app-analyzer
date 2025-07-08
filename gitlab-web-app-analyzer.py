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


class GitLabAnalyzer:
    """Main analyzer class for GitLab repositories"""
    
    def __init__(self, gitlab_url: str, token: Optional[str] = None, rate_limit: float = 2.0):
        self.gitlab_url = gitlab_url
        self.rate_limit = rate_limit
        self.last_request_time = 0
        
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
            
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        min_interval = 1.0 / self.rate_limit
        
        if time_since_last < min_interval:
            time.sleep(min_interval - time_since_last)
        
        self.last_request_time = time.time()
    
    def get_repositories(self, name_filter: Optional[str] = None) -> List[Any]:
        """Get list of repositories with optional name filtering"""
        try:
            click.echo("Fetching repositories from GitLab API...")
            self._rate_limit_wait()
            click.echo("Making API request...")
            # Get projects owned by or accessible to the authenticated user
            projects = self.gl.projects.list(membership=True, per_page=100)
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
                self._rate_limit_wait()
                file_info = project_obj.files.get(file_path, ref=branch_name)
                return file_info.decode().decode('utf-8')
            except:
                continue
        
        return None
    
    def _find_relevant_files(self, project_obj: Any) -> List[str]:
        """Efficiently find relevant web app files using targeted search instead of full recursive scan"""
        file_names = []
        
        # Define the files we're looking for
        target_files = [
            'package.json', 'requirements.txt', 'pyproject.toml', 'pom.xml', 'build.gradle',
            'go.mod', 'main.go', 'composer.json', 'index.php', 'web.config', 'Dockerfile',
            'serverless.yml', 'host.json', 'local.settings.json'
        ]
        
        # Define common subdirectory patterns where web app files are typically found
        search_paths = [
            '',  # Root directory
            'api', 'backend', 'server', 'src', 'app', 'web', 'frontend', 'client', 'ui',
            'java-api', 'node-api', 'python-api', 'web-app', 'webapp', 'website',
            'services', 'microservices', 'functions', 'lambda',
            # Go specific paths
            'cmd', 'cmd/server', 'cmd/main', 'cmd/api',
            # .NET specific paths for enterprise projects
            'src/Presentation', 'src/Web', 'src/WebApi', 'src/Application',
            'Presentation', 'Web', 'WebApi', 'Application',
            # Sample/example directories (common in framework repositories)
            'example', 'examples', 'sample', 'samples', 'demo', 'demos',
            'samples/springboot3/pet-store', 'samples/spring', 'samples/jersey',
            # Spring Guide directories (common in official Spring guides)
            'complete', 'initial'
        ]
        
        
        try:
            # First, get a shallow tree to see what directories exist (much faster)
            self._rate_limit_wait(skip_if_cached=True)
            shallow_tree = project_obj.repository_tree(get_all=True, recursive=False)
            
            # Find directories that match our search patterns
            existing_dirs = set()
            multi_level_dirs = set()  # For paths like src/Presentation
            
            for item in shallow_tree:
                if item.get('type') == 'tree':  # Directory
                    dir_name = item.get('name', '')
                    if dir_name in search_paths[1:]:  # Skip empty string (root)
                        existing_dirs.add(dir_name)
                    
                    # Check for multi-level paths (e.g., if we see 'src', check for 'src/Presentation')
                    for path in search_paths:
                        if '/' in path and path.startswith(dir_name + '/'):
                            multi_level_dirs.add(path)
                            
                elif item.get('type') == 'blob':  # File in root
                    file_name = item.get('name', '')
                    if file_name in target_files:
                        file_names.append(file_name)
                    elif file_name.endswith('.csproj') or file_name.endswith('.sln'):
                        file_names.append(file_name)
            
            # Now check each existing directory for our target files
            for dir_name in existing_dirs:
                try:
                    self._rate_limit_wait(skip_if_cached=True)
                    dir_tree = project_obj.repository_tree(path=dir_name, get_all=True, recursive=False)
                    
                    for item in dir_tree:
                        if item.get('type') == 'blob':
                            file_name = item.get('name', '')
                            if file_name in target_files:
                                file_names.append(f"{dir_name}/{file_name}")
                            elif file_name.endswith('.csproj') or file_name.endswith('.sln'):
                                file_names.append(f"{dir_name}/{file_name}")
                        elif item.get('type') == 'tree':
                            # For .NET projects, also check subdirectories (2nd level) for .csproj files
                            subdir_name = item.get('name', '')
                            try:
                                self._rate_limit_wait(skip_if_cached=True)
                                subdir_tree = project_obj.repository_tree(path=f"{dir_name}/{subdir_name}", get_all=True, recursive=False)
                                
                                for subitem in subdir_tree:
                                    if subitem.get('type') == 'blob':
                                        subfile_name = subitem.get('name', '')
                                        if subfile_name in target_files:
                                            file_names.append(f"{dir_name}/{subdir_name}/{subfile_name}")
                                        elif subfile_name.endswith('.csproj') or subfile_name.endswith('.sln'):
                                            file_names.append(f"{dir_name}/{subdir_name}/{subfile_name}")
                            except Exception:
                                # If we can't access this subdirectory, continue
                                continue
                except Exception:
                    # If we can't access this directory, continue with others
                    continue
            
            # Check multi-level directories (e.g., src/Presentation)
            for multi_path in multi_level_dirs:
                try:
                    self._rate_limit_wait(skip_if_cached=True)
                    multi_tree = project_obj.repository_tree(path=multi_path, get_all=True, recursive=False)
                    
                    for item in multi_tree:
                        if item.get('type') == 'blob':
                            file_name = item.get('name', '')
                            if file_name in target_files:
                                file_names.append(f"{multi_path}/{file_name}")
                            elif file_name.endswith('.csproj') or file_name.endswith('.sln'):
                                file_names.append(f"{multi_path}/{file_name}")
                        elif item.get('type') == 'tree':
                            # For enterprise .NET projects, check one more level deeper
                            subdir_name = item.get('name', '')
                            try:
                                self._rate_limit_wait(skip_if_cached=True)
                                subdir_tree = project_obj.repository_tree(path=f"{multi_path}/{subdir_name}", get_all=True, recursive=False)
                                
                                for subitem in subdir_tree:
                                    if subitem.get('type') == 'blob':
                                        subfile_name = subitem.get('name', '')
                                        if subfile_name in target_files:
                                            file_names.append(f"{multi_path}/{subdir_name}/{subfile_name}")
                                        elif subfile_name.endswith('.csproj') or subfile_name.endswith('.sln'):
                                            file_names.append(f"{multi_path}/{subdir_name}/{subfile_name}")
                            except Exception:
                                continue
                except Exception:
                    continue
                    
        except Exception:
            # If shallow tree fails, fall back to checking just root level files
            try:
                # Get branch names to try
                branch_names = ['main', 'master']
                try:
                    default_branch = project_obj.default_branch
                    if default_branch and default_branch not in branch_names:
                        branch_names.insert(0, default_branch)
                except:
                    pass
                
                for file_name in target_files:
                    for branch_name in branch_names:
                        try:
                            # Try to access file directly - this is very fast
                            file_info = project_obj.files.get(file_name, ref=branch_name)
                            if file_info:
                                file_names.append(file_name)
                                break  # Found file, stop trying other branches
                        except:
                            continue
            except Exception:
                pass
        
        return file_names
    
    def analyze_repository(self, project: Any) -> Dict[str, Any]:
        """Analyze a single repository for web app characteristics"""
        try:
            self._rate_limit_wait()
            full_project = self.gl.projects.get(project.id)
            
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
            result['date_created'] = full_project.created_at.split('T')[0] if full_project.created_at else ''
            
            # Repository size removed for performance (was heavy API call)
            
            # Get languages
            try:
                self._rate_limit_wait()
                languages = full_project.languages()
                if languages:
                    lang_list = [f"{lang}: {count}%" for lang, count in sorted(languages.items(), key=lambda x: x[1], reverse=True)]
                    result['languages'] = ', '.join(lang_list)
            except:
                pass
            
            # Commit analysis removed for performance (was heavy API call)
            
            # Analyze for web app characteristics using cached project object
            web_analysis = self._analyze_web_app_type(full_project)
            result.update(web_analysis)
            
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
                    
                    # Check for web frameworks
                    node_frameworks = {
                        'express': 'Express',
                        'fastify': 'Fastify', 
                        'koa': 'Koa',
                        '@nestjs/core': 'NestJS',
                        'next': 'Next.js'
                    }
                    
                    frontend_frameworks = {
                        'react': 'React',
                        'vue': 'Vue.js',
                        '@angular/core': 'Angular'
                    }
                    
                    # Check for backend Node.js frameworks
                    node_backend_found = False
                    for dep, framework in node_frameworks.items():
                        if dep in deps:
                            analysis['is_web_app'] = 'YES'
                            analysis['web_app_type'] = 'Node.js'
                            analysis['backend_framework'] = framework
                            analysis['package_manager'] = 'npm'
                            confidence_score += 30
                            evidence.append(f'Found {framework} in package.json')
                            node_backend_found = True
                            break  # Found backend framework, stop checking backend
                    
                    # Check for frontend frameworks (independent of backend detection)
                    for dep, framework in frontend_frameworks.items():
                        if dep in deps:
                            if not node_backend_found:
                                # If only frontend found, still mark as web app
                                analysis['is_web_app'] = 'YES'
                                analysis['web_app_type'] = 'Frontend'
                            analysis['frontend_framework'] = framework
                            confidence_score += 20
                            evidence.append(f'Found {framework} frontend framework')
                    
                    # Continue to check for additional frameworks instead of early termination
                            
                except json.JSONDecodeError:
                    pass
            
            # Continue checking other package.json files for additional frameworks
        
        # Check for Python web frameworks (only if files exist)
        if 'requirements.txt' in file_names:
            requirements_txt = self.get_file_content(project_obj, 'requirements.txt')
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
        
        # Early termination if we have high confidence detection AND no need for frontend checking
        if confidence_score >= 30 and not package_json_files:
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
                    # Don't return here - continue checking for frontend frameworks
            
            # Continue checking other pom.xml files for additional frameworks
        
        # Priority 3: Check Go (go.mod - very reliable)
        if 'go.mod' in file_names:
            go_mod = self.get_file_content(project_obj, 'go.mod')
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
            composer_json = self.get_file_content(project_obj, 'composer.json')
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
            pyproject_toml = self.get_file_content(project_obj, 'pyproject.toml')
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
        
        # Check for .NET Core (use existing file list)
        csproj_files = [f for f in file_names if f.endswith('.csproj')]
        
        for csproj_file in csproj_files:
            csproj_content = self.get_file_content(project_obj, csproj_file)
            if csproj_content:
                if 'Microsoft.AspNetCore' in csproj_content or 'AspNetCore' in csproj_content:
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Core'
                    analysis['backend_framework'] = 'ASP.NET Core'
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 30
                    evidence.append('Found ASP.NET Core in .csproj')
                    break
                elif 'System.Web' in csproj_content:
                    analysis['is_web_app'] = 'YES'
                    analysis['web_app_type'] = '.NET Framework'
                    analysis['backend_framework'] = 'ASP.NET'
                    analysis['package_manager'] = 'NuGet'
                    confidence_score += 30
                    evidence.append('Found ASP.NET Framework in .csproj')
                    break
        
        # Check for .NET Solution files (.sln) if no .csproj found
        if not analysis['backend_framework']:
            sln_files = [f for f in file_names if f.endswith('.sln')]
            
            # If no .sln files found in our targeted search, do a broader search of all first-level directories
            if not sln_files:
                try:
                    self._rate_limit_wait(skip_if_cached=True)
                    shallow_tree = project_obj.repository_tree(get_all=True, recursive=False)
                    
                    for item in shallow_tree:
                        if item.get('type') == 'tree':  # Directory
                            dir_name = item.get('name', '')
                            try:
                                self._rate_limit_wait(skip_if_cached=True)
                                dir_tree = project_obj.repository_tree(path=dir_name, get_all=True, recursive=False)
                                
                                for dir_item in dir_tree:
                                    if dir_item.get('type') == 'blob':
                                        file_name = dir_item.get('name', '')
                                        if file_name.endswith('.sln'):
                                            sln_files.append(f"{dir_name}/{file_name}")
                            except Exception:
                                continue
                except Exception:
                    pass
            
            for sln_file in sln_files:
                sln_content = self.get_file_content(project_obj, sln_file)
                if sln_content:
                    # First check for direct web indicators in the solution file
                    web_indicators_sln = [
                        '.Web', '.Website', '.WebApi', '.Mvc', 'AspNet', 'System.Web',
                        'Microsoft.AspNet', 'Web.csproj', 'Website.csproj'
                    ]
                    
                    web_found = any(indicator in sln_content for indicator in web_indicators_sln)
                    
                    # If no direct indicators, extract and analyze .csproj files referenced in the solution
                    if not web_found:
                        import re
                        # Extract .csproj file paths from the solution file
                        csproj_pattern = r'"([^"]*\.csproj)"'
                        csproj_matches = re.findall(csproj_pattern, sln_content)
                        
                        for csproj_match in csproj_matches:
                            # Convert Windows paths to Unix paths and make them relative to the solution directory
                            csproj_path = csproj_match.replace('\\', '/')
                            
                            # If the .sln file is in a subdirectory, adjust the .csproj path
                            if '/' in sln_file:
                                sln_dir = '/'.join(sln_file.split('/')[:-1])
                                full_csproj_path = f"{sln_dir}/{csproj_path}"
                            else:
                                full_csproj_path = csproj_path
                            
                            try:
                                csproj_content = self.get_file_content(project_obj, full_csproj_path)
                                if csproj_content:
                                    # Check for web-related content in the .csproj file
                                    web_indicators_csproj = [
                                        'Microsoft.AspNetCore', 'System.Web', 'AspNet',
                                        'System.Web.Mvc', 'System.Web.WebPages',
                                        'Microsoft.Web.Infrastructure', 'WebApplication',
                                        'Microsoft.AspNet', 'Web.config', 'Global.asax'
                                    ]
                                    
                                    if any(indicator in csproj_content for indicator in web_indicators_csproj):
                                        web_found = True
                                        break
                            except Exception:
                                continue
                    
                    if web_found:
                        analysis['is_web_app'] = 'YES'
                        
                        # Try to determine if it's .NET Core or Framework based on solution content
                        if 'Microsoft.AspNetCore' in sln_content or 'netcore' in sln_content.lower():
                            analysis['web_app_type'] = '.NET Core'
                            analysis['backend_framework'] = 'ASP.NET Core'
                        else:
                            analysis['web_app_type'] = '.NET Framework'
                            analysis['backend_framework'] = 'ASP.NET'
                            
                        analysis['package_manager'] = 'NuGet'
                        confidence_score += 25
                        evidence.append(f'Found web project references in {sln_file}')
                        break
        
        # Check for web.config (ASP.NET) (only if it exists and no backend found yet)
        if 'web.config' in file_names and not analysis['backend_framework']:
            web_config = self.get_file_content(project_obj, 'web.config')
            if web_config:
                analysis['is_web_app'] = 'YES'
                analysis['web_app_type'] = '.NET Framework'
                analysis['backend_framework'] = 'ASP.NET'
                analysis['web_server_os'] = 'Windows'
                confidence_score += 25
                evidence.append('Found web.config file')
        
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
        
        # Check for Docker/web servers (only if files exist)
        if 'Dockerfile' in file_names:
            dockerfile = self.get_file_content(project_obj, 'Dockerfile')
            if dockerfile:
                if 'nginx' in dockerfile.lower():
                    analysis['web_server'] = 'Nginx'
                    confidence_score += 10
                    evidence.append('Found Nginx in Dockerfile')
                elif 'apache' in dockerfile.lower():
                    analysis['web_server'] = 'Apache'
                    confidence_score += 10
                    evidence.append('Found Apache in Dockerfile')
                
                # Detect OS
                if 'FROM ubuntu' in dockerfile or 'FROM debian' in dockerfile:
                    analysis['web_server_os'] = 'Linux'
                elif 'FROM alpine' in dockerfile:
                    analysis['web_server_os'] = 'Linux'
                elif 'FROM windows' in dockerfile:
                    analysis['web_server_os'] = 'Windows'
        
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


@click.command()
@click.option('--gitlab-url', help='GitLab instance URL')
@click.option('--token', help='Personal access token')
@click.option('--output', help='Output CSV filename')
@click.option('--filter', 'name_filter', default=None, help='Repository name filter (default: all repositories)')
@click.option('--rate-limit', default=5.0, help='Requests per second (default: 5)')
def main(gitlab_url, token, output, name_filter, rate_limit):
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
        analyzer = GitLabAnalyzer(gitlab_url, token, rate_limit)
        
        # Get repositories
        click.echo("Fetching repositories...")
        repositories = analyzer.get_repositories(name_filter)
        click.echo(f"Found {len(repositories)} repositories to analyze")
        
        # Analyze repositories
        results = []
        with click.progressbar(repositories, label='Analyzing repositories') as repos:
            for repo in repos:
                result = analyzer.analyze_repository(repo)
                results.append(result)
        
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
        
    except Exception as e:
        raise click.ClickException(f"Analysis failed: {e}")


if __name__ == '__main__':
    main()  # type: ignore