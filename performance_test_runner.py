import requests
import time
import random
import yaml
import json
import os
import argparse
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import re

class ValueProviderType(Enum):
    STATIC = "static"
    RANDOM_INT = "random_int"
    RANDOM_FLOAT = "random_float"
    RANDOM_STRING = "random_string"
    RANDOM_BOOL = "random_bool"
    RANDOM_CHOICE = "random_choice"
    WEIGHTED_CHOICE = "weighted_choice"
    UUID = "uuid"
    TIMESTAMP = "timestamp"
    LOREM_IPSUM = "lorem_ipsum"
    RANDOM_EMAIL = "random_email"
    RANGE = "range"
    NOW = "now"

class ValueProvider:
    """Factory class for dynamic value providers"""
    
    @staticmethod
    def get_provider(value: Any) -> Callable[[], Any]:
        """Get a provider function based on the value pattern"""
        if not isinstance(value, str):
            return lambda: value
            
        # Check for $random{...} pattern
        random_match = re.match(r'\$random\{([^}]+)\}', value)
        if random_match:
            choices = [x.strip() for x in random_match.group(1).split(',')]
            if len(choices) == 2 and all(x.strip().lstrip('-').replace('.', '', 1).isdigit() for x in choices):
                # Numeric range
                if any('.' in x for x in choices):
                    min_val, max_val = map(float, choices)
                    return lambda: round(random.uniform(min_val, max_val), 2)
                else:
                    min_val, max_val = map(int, choices)
                    return lambda: random.randint(min_val, max_val)
            else:
                # String choice
                return lambda: random.choice(choices)
                
        # Check for $uuid
        if value == "$uuid":
            return lambda: str(uuid.uuid4())
            
        # Check for $now
        if value == "$now":
            return lambda: datetime.now(timezone.utc).isoformat()
            
        # Check for $lorem{N}
        lorem_match = re.match(r'\$lorem\{(\d+)\}', value)
        if lorem_match:
            word_count = int(lorem_match.group(1))
            return lambda: ' '.join(['lorem'] * word_count)  # Simplified for example
            
        # Check for $random{type} patterns
        type_match = re.match(r'\$(\w+)\{([^}]*)\}', value)
        if type_match:
            provider_type = type_match.group(1)
            params = type_match.group(2)
            
            if provider_type == 'range':
                # Handle $range{min,max} or $range{range_name}
                if params.isalpha() and params in ('price_range', 'user_age'):
                    # Get from config ranges
                    return lambda: random.randint(10, 1000)  # Simplified - should get from config
                else:
                    min_val, max_val = map(int, params.split(','))
                    return lambda: random.randint(min_val, max_val)
                    
            elif provider_type == 'random':
                # Already handled by the first pattern
                pass
                
        # No provider found, return as-is
        return lambda: value

@dataclass
class TestConfig:
    base_url: str
    endpoints: List[Dict[str, Any]]
    num_workers: int = 10
    requests_per_endpoint: int = 100
    num_test_runs: int = 5
    default_headers: Dict[str, str] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    generators: Dict[str, Any] = field(default_factory=dict)
    datasets: Dict[str, Any] = field(default_factory=dict)
    ranges: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TestResult:
    endpoint: str
    method: str
    success: bool
    status_code: Optional[int]
    response_time: float  # in milliseconds
    error: Optional[str] = None
    request_data: Optional[Dict] = None

class PerformanceTester:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.session = requests.Session()
        
        # Set default headers for all requests
        if self.config.default_headers:
            self.session.headers.update(self.config.default_headers)
    
    def _load_config(self, config_path: str) -> TestConfig:
        """Load test configuration from YAML file."""
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        return TestConfig(**config_data)
    
    def _resolve_variables(self, value: Any) -> Any:
        """Resolve variables and dynamic values in the configuration."""
        if isinstance(value, str):
            # Handle dynamic value providers
            if value.startswith('$'):
                provider = ValueProvider.get_provider(value)
                return provider()
                
            # Handle variable substitution ${var_name}
            var_match = re.findall(r'\${([^}]+)}', value)
            if var_match:
                result = value
                for var_name in var_match:
                    # Check in different sections of config
                    var_value = (
                        self.config.variables.get(var_name) or
                        self.config.generators.get(var_name) or
                        self.config.datasets.get(var_name) or
                        self.config.ranges.get(var_name) or
                        f'${{{var_name}}}'  # Not found, keep as is
                    )
                    result = result.replace(f'${{{var_name}}}', str(var_value))
                return result
                
        elif isinstance(value, dict):
            return {k: self._resolve_variables(v) for k, v in value.items()}
            
        elif isinstance(value, list):
            return [self._resolve_variables(item) for item in value]
            
        return value
    
    def _generate_request_data(self, endpoint_config: Dict[str, Any]) -> Dict:
        """Generate request data with resolved variables."""
        if 'data' not in endpoint_config:
            return {}
        
        data = endpoint_config['data']
        if isinstance(data, str) and data.startswith('@'):
            # Load data from file
            file_path = data[1:]
            with open(file_path, 'r') as f:
                if file_path.endswith('.json'):
                    data = json.load(f)
                else:
                    data = f.read()
        
        return self._resolve_variables(data)
    
    def _generate_url(self, base_url: str, path: str) -> str:
        """Generate full URL from base URL and path."""
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    
    def _send_request(self, method: str, url: str, **kwargs) -> TestResult:
        """Send a single HTTP request and return the result."""
        start_time = time.perf_counter()
        try:
            response = self.session.request(method, url, **kwargs)
            response_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
            response.raise_for_status()
            return TestResult(
                endpoint=url,
                method=method,
                success=True,
                status_code=response.status_code,
                response_time=response_time
            )
        except requests.exceptions.RequestException as e:
            response_time = (time.perf_counter() - start_time) * 1000
            status_code = e.response.status_code if hasattr(e, 'response') and e.response else None
            return TestResult(
                endpoint=url,
                method=method,
                success=False,
                status_code=status_code,
                response_time=response_time,
                error=str(e),
                request_data=kwargs.get('json', kwargs.get('data'))
            )
    
    def test_endpoint(self, endpoint_config: Dict[str, Any]) -> List[TestResult]:
        """Test a single endpoint according to its configuration."""
        results = []
        method = endpoint_config.get('method', 'GET').upper()
        url = self._generate_url(self.config.base_url, endpoint_config['path'])
        
        # Generate request data
        request_data = self._generate_request_data(endpoint_config)
        
        # Set up request kwargs
        kwargs = {}
        if method in ['POST', 'PUT', 'PATCH'] and request_data:
            kwargs['json' if endpoint_config.get('json_content', True) else 'data'] = request_data
        
        # Send requests
        for _ in range(self.config.requests_per_endpoint):
            result = self._send_request(method, url, **kwargs)
            results.append(result)
            
            # Add delay between requests if specified
            if 'delay' in endpoint_config:
                time.sleep(endpoint_config.get('delay', 0) / 1000)  # Convert ms to seconds
        
        return results
    
    def run_tests(self) -> Dict[str, Any]:
        """Run all configured tests and return results."""
        all_results = []
        
        with ThreadPoolExecutor(max_workers=self.config.num_workers) as executor:
            futures = []
            
            # Submit all test cases
            for endpoint in self.config.endpoints:
                futures.append(executor.submit(self.test_endpoint, endpoint))
            
            # Collect results as they complete
            for future in as_completed(futures):
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    print(f"Error in test execution: {str(e)}")
        
        # Calculate statistics
        successful = [r for r in all_results if r.success]
        failed = [r for r in all_results if not r.success]
        response_times = [r.response_time for r in successful]
        
        return {
            'total_requests': len(all_results),
            'successful_requests': len(successful),
            'failed_requests': len(failed),
            'min_time': min(response_times) if response_times else 0,
            'max_time': max(response_times) if response_times else 0,
            'avg_time': sum(response_times) / len(response_times) if response_times else 0,
            'response_times': response_times,
            'errors': [{'endpoint': r.endpoint, 'error': r.error} for r in failed]
        }

def generate_html_report(stats: Dict, output_dir: str = 'reports', is_aggregated: bool = False) -> str:
    """Generate an HTML report from test statistics."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = os.path.join(output_dir, f'performance_report_{timestamp}.html')
    
    # Calculate success rate safely
    total_requests = stats.get('total_requests', 0)
    successful_requests = stats.get('successful_requests', 0)
    failed_requests = stats.get('failed_requests', 0)
    
    # Handle cases where there are no successful requests
    has_successful = successful_requests > 0
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Performance Test Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .metric {{ margin: 10px 0; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
            .warning {{ color: orange; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            pre {{ background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <h1>Performance Test Report</h1>
        <div class="summary">
            <h2>Summary</h2>
            <div class="metric">Total Requests: {total_requests}</div>
            <div class="metric {success_class}">Successful: {successful_requests}</div>
            <div class="metric {error_class}">Failed: {failed_requests}</div>
            <div class="metric">Success Rate: {success_rate:.2f}%</div>
    """.format(
        total_requests=total_requests,
        successful_requests=successful_requests,
        failed_requests=failed_requests,
        success_rate=(successful_requests / total_requests * 100) if total_requests > 0 else 0,
        success_class="success" if successful_requests > 0 else "error",
        error_class="error" if failed_requests > 0 else ""
    )
    
    # Add response time metrics only if there were successful requests
    if has_successful:
        html += f"""
            <div class="metric">Average Response Time: {stats.get('avg_time', 0):.2f} ms</div>
            <div class="metric">Min Response Time: {stats.get('min_time', 0):.2f} ms</div>
            <div class="metric">Max Response Time: {stats.get('max_time', 0):.2f} ms</div>
        """
        
        # Add individual run stats if this is an aggregated report
        if is_aggregated and 'individual_runs' in stats:
            html += """
                <div class="metric">
                    <h3>Individual Run Statistics</h3>
                    <table>
                        <tr>
                            <th>Run #</th>
                            <th>Success Rate</th>
                            <th>Avg Response Time (ms)</th>
                        </tr>
            """
            
            for run in stats['individual_runs']:
                html += f"""
                    <tr>
                        <td>{run['run']}</td>
                        <td>{run['success_rate']:.2f}%</td>
                        <td>{run['avg_time']:.2f}</td>
                    </tr>
                """
            
            html += """
                    </table>
                </div>
            """
    else:
        html += """
            <div class="metric warning">No successful requests to calculate response times</div>
        """
    
    html += "</div>"  # Close summary div
    
    # Add errors section if any
    errors = stats.get('errors', []) if not is_aggregated else (stats.get('all_errors', [])[:50])  # Limit to 50 errors in aggregated report
    if errors:
        html += "<h2>Error Details</h2>"
        html += "<p>First few errors encountered:</p>"
        html += "<table><tr><th>#</th><th>Endpoint</th><th>Status Code</th><th>Error</th></tr>"
        for i, error in enumerate(errors[:10], 1):  # Show first 10 errors
            status_code = error.get('status_code', 'N/A')
            endpoint = error.get('endpoint', 'Unknown')
            error_msg = error.get('error', 'No error details available')
            
            # Truncate long error messages
            if len(str(error_msg)) > 100:
                error_msg = str(error_msg)[:100] + '...'
                
            html += f"""
            <tr>
                <td>{i}</td>
                <td>{endpoint}</td>
                <td>{status_code}</td>
                <td><pre>{error_msg}</pre></td>
            </tr>"""
        
        if len(errors) > 10:
            html += f"<tr><td colspan='4'>... and {len(errors) - 10} more errors (showing first 10)</td></tr>"
            
        html += "</table>"
        
        # Add debugging tips if all requests failed
        if successful_requests == 0 and total_requests > 0 and not is_aggregated:
            html += """
            <div style="margin-top: 20px; padding: 15px; background-color: #fff3cd; border-left: 5px solid #ffc107;">
                <h3>Debugging Tips</h3>
                <ul>
                    <li>Check if the API server is running and accessible</li>
                    <li>Verify the base URL in the configuration</li>
                    <li>Check if authentication is required and credentials are correct</li>
                    <li>Inspect the error messages above for more details</li>
                    <li>Try testing the endpoints manually with a tool like curl or Postman</li>
                </ul>
            </div>
            """
    
    html += "</body></html>"
    
    with open(report_path, 'w') as f:
        f.write(html)
    
    return report_path

def aggregate_results(all_stats: List[Dict]) -> Dict:
    """Aggregate results from multiple test runs."""
    if not all_stats:
        return {}
    
    # Initialize aggregated stats
    aggregated = {
        'total_runs': len(all_stats),
        'total_requests': 0,
        'successful_requests': 0,
        'failed_requests': 0,
        'response_times': [],
        'all_errors': [],
        'run_stats': []
    }
    
    # Aggregate data from all runs
    for stats in all_stats:
        aggregated['total_requests'] += stats.get('total_requests', 0)
        aggregated['successful_requests'] += stats.get('successful_requests', 0)
        aggregated['failed_requests'] += stats.get('failed_requests', 0)
        
        if 'response_times' in stats and stats['response_times']:
            aggregated['response_times'].extend(stats['response_times'])
        
        if 'errors' in stats:
            aggregated['all_errors'].extend(stats['errors'])
        
        # Store individual run stats
        aggregated['run_stats'].append({
            'success_rate': (stats.get('successful_requests', 0) / stats.get('total_requests', 1)) * 100,
            'avg_time': stats.get('avg_time', 0),
            'min_time': stats.get('min_time', 0),
            'max_time': stats.get('max_time', 0)
        })
    
    # Calculate aggregated metrics
    if aggregated['response_times']:
        aggregated['avg_time'] = sum(aggregated['response_times']) / len(aggregated['response_times'])
        aggregated['min_time'] = min(aggregated['response_times'])
        aggregated['max_time'] = max(aggregated['response_times'])
    else:
        aggregated['avg_time'] = 0
        aggregated['min_time'] = 0
        aggregated['max_time'] = 0
    
    # Calculate success rate across all runs
    if aggregated['total_requests'] > 0:
        aggregated['success_rate'] = (aggregated['successful_requests'] / aggregated['total_requests']) * 100
    else:
        aggregated['success_rate'] = 0
    
    return aggregated

def main():
    parser = argparse.ArgumentParser(description='Run performance tests')
    parser.add_argument('--config', type=str, default='config.yaml',
                       help='Path to the test configuration file (default: config.yaml)')
    parser.add_argument('--output', type=str, default='reports',
                       help='Output directory for reports (default: reports)')
    
    args = parser.parse_args()
    
    try:
        tester = PerformanceTester(args.config)
        print(f"Running performance tests with {tester.config.num_workers} workers...")
        
        all_stats = []
        
        # Run tests multiple times if specified
        for run in range(1, tester.config.num_test_runs + 1):
            print(f"\n--- Test Run {run}/{tester.config.num_test_runs} ---")
            stats = tester.run_tests()
            all_stats.append(stats)
            
            # Print summary for this run
            print(f"\nTest Run {run} Summary:")
            print(f"  Total Requests: {stats['total_requests']}")
            print(f"  Successful: {stats['successful_requests']}")
            print(f"  Failed: {stats['failed_requests']}")
            print(f"  Success Rate: {(stats['successful_requests'] / stats['total_requests'] * 100):.2f}%")
            print(f"  Avg Response Time: {stats.get('avg_time', 0):.2f} ms")
        
        # Generate a single comprehensive report for all runs
        if all_stats:
            aggregated = aggregate_results(all_stats)
            
            # Add individual run stats to the aggregated results
            aggregated['individual_runs'] = [
                {
                    'run': i + 1,
                    'success_rate': run_stats['success_rate'],
                    'avg_time': run_stats['avg_time']
                }
                for i, run_stats in enumerate(aggregated['run_stats'])
            ]
            
            # Generate the final report
            report_path = generate_html_report(aggregated, args.output, is_aggregated=True)
            print(f"\nComprehensive report generated: {report_path}")
    
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
