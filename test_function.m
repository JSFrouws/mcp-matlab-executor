function result = test_function(a, b)
% TEST_FUNCTION Simple test function for the MATLAB Executor MCP tool
%   This function adds two numbers and returns the result
%   Usage: test_function(2, 3) returns 5

    fprintf('Running test_function with arguments: %f and %f\n', a, b);
    result = a + b;
    fprintf('Result: %f\n', result);
end
