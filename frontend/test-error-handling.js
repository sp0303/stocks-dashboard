#!/usr/bin/env node

/**
 * Error Handling Integration Test Suite for AccountManager
 * This script validates all 8 error handling paths in the AccountManager component
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Color codes for terminal output
const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
};

// Test tracking
const tests = [];
let passCount = 0;
let failCount = 0;

// Helper functions
function test(name, fn) {
  tests.push({ name, fn });
}

function expect(value) {
  return {
    toBe(expected) {
      if (value !== expected) {
        throw new Error(`Expected ${expected} but got ${value}`);
      }
    },
    toInclude(substring) {
      if (!value.includes(substring)) {
        throw new Error(`Expected to include "${substring}" but got "${value}"`);
      }
    },
    toExist() {
      if (!value) {
        throw new Error(`Expected value to exist but got ${value}`);
      }
    },
    toBeNull() {
      if (value !== null) {
        throw new Error(`Expected null but got ${value}`);
      }
    },
    toBeUndefined() {
      if (value !== undefined) {
        throw new Error(`Expected undefined but got ${value}`);
      }
    },
    toEqual(expected) {
      if (JSON.stringify(value) !== JSON.stringify(expected)) {
        throw new Error(`Expected ${JSON.stringify(expected)} but got ${JSON.stringify(value)}`);
      }
    },
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// CODE ANALYSIS TESTS
// ═══════════════════════════════════════════════════════════════════════════════

test('Error Path 1: Missing Account Name - Should validate empty name', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  // Check for name validation
  expect(componentCode).toInclude('if (!formData.name.trim())');
  expect(componentCode).toInclude('Account name is required');
  expect(componentCode).toInclude('setError(\'Account name is required\')');
});

test('Error Path 2a: Missing API Key - Should validate required credentials', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  // Check for credentials validation
  expect(componentCode).toInclude('!formData.api_key.trim()');
  expect(componentCode).toInclude('All Kite credentials are required');
});

test('Error Path 2b: Missing API Secret - Should validate all required fields', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  expect(componentCode).toInclude('!formData.api_secret.trim()');
  expect(componentCode).toInclude('All Kite credentials are required');
});

test('Error Path 2c: Missing User ID - Should validate all required fields', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  expect(componentCode).toInclude('!formData.user_id.trim()');
  expect(componentCode).toInclude('All Kite credentials are required');
});

test('Error Path 2d: Missing Password - Should validate all required fields', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  expect(componentCode).toInclude('!formData.password.trim()');
  expect(componentCode).toInclude('All Kite credentials are required');
});

test('Error Path 2e: Missing TOTP Secret - Should validate all required fields', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  expect(componentCode).toInclude('!formData.totp_secret.trim()');
  expect(componentCode).toInclude('All Kite credentials are required');
});

test('Error Path 3: API Error Response - Should handle errors in handleAddAccount', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  // Check for try-catch block in handleAddAccount
  expect(componentCode).toInclude('handleAddAccount(e)');
  expect(componentCode).toInclude('await api.kiteAddAccount(clientId, formData)');
  expect(componentCode).toInclude('} catch (err) {');
  expect(componentCode).toInclude('setError(err.message)');
  expect(componentCode).toInclude('} finally {');
  expect(componentCode).toInclude('setLoading(false)');
});

test('Error Path 4: Network Error - Should reset loading state in finally block', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  // Check that finally block ensures loading is reset
  const handleAddAccountMatch = componentCode.match(
    /async function handleAddAccount[\s\S]*?finally \{[\s\S]*?setLoading\(false\)/
  );
  expect(handleAddAccountMatch).toExist();
});

test('Error Path 5: Delete Account Error - Should handle delete failures', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  // Check for error handling in handleDeleteAccount
  expect(componentCode).toInclude('handleDeleteAccount(accountId)');
  expect(componentCode).toInclude('await api.kiteDeleteAccount(clientId, accountId)');
  expect(componentCode).toInclude('setError(err.message)');
});

test('Error Path 6: Sync Account Error - Should handle sync failures gracefully', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  // Check for error handling in handleSyncAccount
  expect(componentCode).toInclude('handleSyncAccount(accountId)');
  expect(componentCode).toInclude('await api.kiteSyncAccount(clientId, accountId)');
  expect(componentCode).toInclude('Error syncing: ');
});

test('Error Path 7: Load Accounts Error - Should handle load failures silently', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  // Check for error handling in loadAccounts
  expect(componentCode).toInclude('async function loadAccounts()');
  expect(componentCode).toInclude('} catch (err) {');
  expect(componentCode).toInclude('console.error(\'Error loading accounts:\', err)');
});

test('Error Path 8: Error State Clearing - Should clear error on new action', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  // Check that setError('') is called at start of async operations
  expect(componentCode).toInclude('handleAddAccount(e)');
  const handlerMatch = componentCode.match(
    /async function handle[A-Za-z]*\(.*?\) \{[\s\S]*?setError\(\'\'\)/
  );
  expect(handlerMatch).toExist();
});

test('API Module: Should properly throw errors with messages', () => {
  const apiCode = fs.readFileSync(
    path.join(__dirname, 'src/api.js'),
    'utf8'
  );

  // Check that req function handles errors
  expect(apiCode).toInclude('if (!res.ok)');
  expect(apiCode).toInclude('throw new Error(msg)');
});

test('UI: Should display error messages in error box', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  // Check for error display component
  expect(componentCode).toInclude('{error && (');
  expect(componentCode).toInclude('className={`error-box');
  expect(componentCode).toInclude('{error}');
});

test('UI: Should differentiate error and success messages', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  // Check for success/error message handling
  expect(componentCode).toInclude('error.startsWith(\'✓\')');
});

test('Form: Should disable submit button during loading', () => {
  const componentCode = fs.readFileSync(
    path.join(__dirname, 'src/components/AccountManager.jsx'),
    'utf8'
  );

  expect(componentCode).toInclude('disabled={loading}');
  expect(componentCode).toInclude('loading ? \'Adding...\' : \'Add Account\'');
});

// ═══════════════════════════════════════════════════════════════════════════════
// RUN TESTS
// ═══════════════════════════════════════════════════════════════════════════════

async function runTests() {
  console.log('\n' + colors.blue + '═'.repeat(80));
  console.log('AccountManager Error Handling Integration Tests');
  console.log('═'.repeat(80) + colors.reset + '\n');

  for (const { name, fn } of tests) {
    try {
      fn();
      passCount++;
      console.log(colors.green + '✓' + colors.reset + ' ' + name);
    } catch (error) {
      failCount++;
      console.log(colors.red + '✗' + colors.reset + ' ' + name);
      console.log(colors.red + '  Error: ' + error.message + colors.reset);
    }
  }

  console.log('\n' + colors.blue + '═'.repeat(80));
  console.log('Test Summary');
  console.log('═'.repeat(80) + colors.reset);

  const total = passCount + failCount;
  const passPercentage = ((passCount / total) * 100).toFixed(1);

  console.log(colors.green + `Passed: ${passCount}/${total}` + colors.reset);
  if (failCount > 0) {
    console.log(colors.red + `Failed: ${failCount}/${total}` + colors.reset);
  }
  console.log(`Pass Rate: ${passPercentage}%`);
  console.log('');

  if (failCount === 0) {
    console.log(colors.green + '✓ All error handling paths are properly implemented!' + colors.reset);
  } else {
    console.log(colors.red + `✗ ${failCount} test(s) failed. Please review the code.` + colors.reset);
  }

  console.log(colors.blue + '═'.repeat(80) + colors.reset + '\n');

  process.exit(failCount > 0 ? 1 : 0);
}

// ═══════════════════════════════════════════════════════════════════════════════
// ERROR PATHS SUMMARY
// ═══════════════════════════════════════════════════════════════════════════════

console.log('\n' + colors.cyan + 'Error Paths Being Tested:' + colors.reset);
console.log(colors.cyan + '1. Missing Account Name' + colors.reset);
console.log(colors.cyan + '2. Missing API Key' + colors.reset);
console.log(colors.cyan + '3. Missing API Secret' + colors.reset);
console.log(colors.cyan + '4. Missing User ID' + colors.reset);
console.log(colors.cyan + '5. Missing Password' + colors.reset);
console.log(colors.cyan + '6. Missing TOTP Secret' + colors.reset);
console.log(colors.cyan + '7. API Error Responses' + colors.reset);
console.log(colors.cyan + '8. Network Errors with Loading State Recovery' + colors.reset);
console.log('');

(async () => {
  await runTests();
})().catch(console.error);
