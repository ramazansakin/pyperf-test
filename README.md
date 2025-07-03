# PyPerf Test 🚀

A high-performance API testing tool with dynamic test data generation for comprehensive load testing and performance analysis.

## Features ✨

- **Dynamic Test Data Generation** - Generate realistic test data on the fly
- **Multi-threaded Execution** - Simulate concurrent users with configurable workers
- **Comprehensive Reporting** - Detailed HTML reports with metrics and error analysis
- **Flexible Configuration** - YAML-based configuration for test scenarios
- **Support for All HTTP Methods** - Test RESTful APIs with any HTTP method
- **Smart Error Handling** - Detailed error reporting and debugging information

## Prerequisites 📋

- Python 3.8+
- pip (Python package manager)

## Installation 🛠️

1. Clone the repository:
   ```bash
   git clone https://github.com/ramazansakin/pyperf-test.git
   cd pyperf-test
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Quick Start 🚀

1. Copy the example configuration:
   ```bash
   cp config.template.yaml config.yaml
   ```

2. Edit `config.yaml` to match your API endpoints and test scenarios.

3. Run the performance tests:
   ```bash
   python performance_test_runner.py --config config.yaml --output reports
   ```

4. View the generated HTML report in the `reports` directory.

## Configuration Guide ⚙️

### Basic Configuration

```yaml
# Base URL of your API
base_url: "https://api.example.com/v1"

# Number of concurrent workers (virtual users)
num_workers: 10

# Number of requests per endpoint configuration
requests_per_endpoint: 100

# Number of test runs
num_test_runs: 3
```

### Dynamic Data Generation

Generate dynamic values in your requests using these patterns:

- `$random{min,max}` - Random number between min and max
- `$random{val1,val2,val3}` - Random selection from values
- `$uuid` - Generate a UUID
- `$now` - Current timestamp
- `$lorem{N}` - N words of lorem ipsum
- `$range{range_name}` - Random number from a defined range

Example:
```yaml
endpoints:
  - name: "Create User"
    method: POST
    path: "/users"
    data:
      id: "$uuid"
      username: "user_$random{1000,9999}"
      email: "user_$random{1000,9999}@example.com"
      created_at: "$now"
      is_active: "$random{true,false}"
```

### Example Configuration

See [config.template.yaml](config.template.yaml) for a complete example with detailed comments.

## Command Line Options 🖥️

```
usage: performance_test_runner.py [-h] [--config CONFIG] [--output OUTPUT]

Performance Test Runner

options:
  -h, --help       show this help message and exit
  --config CONFIG  Path to the test configuration file (default: config.yaml)
  --output OUTPUT  Output directory for reports (default: reports)
```

## Understanding the Report 📊

The HTML report includes:

- **Summary Statistics**: Total requests, success rate, response times
- **Response Time Distribution**: Visual representation of response times
- **Error Analysis**: Detailed error messages and status codes
- **Performance Metrics**: Min, max, and average response times
- **Test Configuration**: Summary of test parameters

## Best Practices 📝

1. **Start Small**: Begin with a small number of users and gradually increase.
2. **Monitor Resources**: Keep an eye on system resources during testing.
3. **Use Realistic Data**: Leverage dynamic data generation for realistic test scenarios.
4. **Test in Staging**: Always test against a staging environment first.
5. **Analyze Results**: Look for patterns in errors and performance bottlenecks.

## Contributing 🤝

Contributions are welcome! Please feel free to submit a Pull Request.

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support 💬

For support, please open an issue in the GitHub repository.
