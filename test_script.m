% Simple test script for the MATLAB Executor MCP tool
disp('Running test script...');

% Create some data
x = linspace(0, 2*pi, 100);
y = sin(x);

% Perform a simple calculation
result = sum(y);
disp(['Sum of sin(x): ', num2str(result)]);

% Display success message
disp('Test script completed successfully!');
