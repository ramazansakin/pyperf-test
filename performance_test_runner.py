import requests
import time
import random
import yaml
import json
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

@dataclass
class TestConfig:
    base_url: str
    endpoints: List[Dict[str, Any]]
    num_workers: int = 10
    requests_per_endpoint: int = 100
    num_test_runs: int = 5
    default_headers: Dict[str, str] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)

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
        """Resolve variables in the configuration."""
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            var_name = value[2:-1]
            return self.config.variables.get(var_name, value)
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

def generate_html_report(stats: Dict, output_dir: str = 'reports'):
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
            body { font-family: Arial, sans-serif; margin: 20px; }
            .summary { background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
            .metric { margin: 10px 0; }
            .success { color: green; }
            .error { color: red; }
            .warning { color: orange; font-weight: bold; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
            tr:nth-child(even) { background-color: #f9f9f9; }
            pre { background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; }
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
        html += """
            <div class="metric">Average Response Time: {avg_time:.2f} ms</div>
            <div class="metric">Min Response Time: {min_time:.2f} ms</div>
            <div class="metric">Max Response Time: {max_time:.2f} ms</div>
        """.format(
            avg_time=stats.get('avg_time', 0),
            min_time=stats.get('min_time', 0),
            max_time=stats.get('max_time', 0)
        )
    else:
        html += """
            <div class="metric warning">No successful requests to calculate response times</div>
        """
    
    html += "</div>"  # Close summary div
    
    # Add errors section if any
    if stats.get('errors'):
        html += "<h2>Error Details</h2>"
        html += "<p>First few errors encountered:</p>"
        html += "<table><tr><th>#</th><th>Endpoint</th><th>Status Code</th><th>Error</th></tr>"
        for i, error in enumerate(stats['errors'][:10], 1):  # Show first 10 errors
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
        
        if len(stats['errors']) > 10:
            html += f"<tr><td colspan='4'>... and {len(stats['errors']) - 10} more errors</td></tr>"
            
        html += "</table>"
        
        # Add debugging tips if all requests failed
        if successful_requests == 0 and total_requests > 0:
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
        
        # Run tests multiple times if specified
        for run in range(1, tester.config.num_test_runs + 1):
            print(f"\n--- Test Run {run}/{tester.config.num_test_runs} ---")
            stats = tester.run_tests()
            
            # Print summary
            print(f"\nTest Run {run} Summary:")
            print(f"  Total Requests: {stats['total_requests']}")
            print(f"  Successful: {stats['successful_requests']}")
            print(f"  Failed: {stats['failed_requests']}")
            print(f"  Success Rate: {(stats['successful_requests'] / stats['total_requests'] * 100):.2f}%")
            print(f"  Avg Response Time: {stats['avg_time']:.2f} ms")
            
            # Generate report for each run
            report_path = generate_html_report(stats, args.output)
            print(f"\nReport generated: {report_path}")
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
