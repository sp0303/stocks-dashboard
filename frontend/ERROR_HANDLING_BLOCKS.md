# AccountManager Error Handling Blocks - Code Reference

## Overview

The AccountManager component contains **8 distinct error handling blocks** across 4 async functions. This document provides a detailed reference for each block.

---

## Error Handling Block 1: Load Accounts - Try-Catch

**Location**: `src/components/AccountManager.jsx` (lines 24-31)  
**Function**: `loadAccounts()`  
**Type**: Silent error logging

```javascript
async function loadAccounts() {
  try {
    const data = await api.kiteListAccounts(clientId)
    setAccounts(data.accounts || [])
  } catch (err) {
    console.error('Error loading accounts:', err)  // BLOCK 1
  }
}
```

**Characteristics**:
- No `finally` block
- No user-facing error display
- Only logs to console for debugging
- Allows app to continue even if load fails
- Called on component mount and after actions

**Test Coverage**: ✓ Verified to log errors without showing UI message

---

## Error Handling Block 2: Add Account - Error Clear

**Location**: `src/components/AccountManager.jsx` (line 36)  
**Function**: `handleAddAccount(e)`  
**Type**: State reset before operation

```javascript
async function handleAddAccount(e) {
  e.preventDefault()
  try {
    setError('')  // BLOCK 2 - Clear previous error
    setLoading(true)
    
    // Validation and API call...
```

**Characteristics**:
- First operation in function
- Clears stale error messages
- Prevents showing previous error during new attempt
- Paired with validation blocks

**Test Coverage**: ✓ Verified to clear error state on new attempts

---

## Error Handling Block 3: Add Account - Name Validation

**Location**: `src/components/AccountManager.jsx` (lines 39-43)  
**Function**: `handleAddAccount(e)`  
**Type**: Input validation with error return

```javascript
      if (!formData.name.trim()) {
        setError('Account name is required')  // BLOCK 3
        setLoading(false)
        return
      }
```

**Characteristics**:
- Validates before credentials check
- Trims whitespace
- Resets loading state before return
- Prevents further execution
- User-friendly message

**Error Message**: "Account name is required"  
**Test Coverage**: ✓ Rejects empty and whitespace-only names

---

## Error Handling Block 4: Add Account - Credentials Validation

**Location**: `src/components/AccountManager.jsx` (lines 44-48)  
**Function**: `handleAddAccount(e)`  
**Type**: Multi-field validation with error return

```javascript
      if (!formData.api_key.trim() || !formData.api_secret.trim() || 
          !formData.user_id.trim() || !formData.password.trim() || 
          !formData.totp_secret.trim()) {
        setError('All Kite credentials are required')  // BLOCK 4
        setLoading(false)
        return
      }
```

**Characteristics**:
- Validates all 5 credential fields
- Uses OR logic (fails if ANY field missing)
- Trims whitespace from each field
- Resets loading state before return
- Single error message for all fields

**Fields Validated**:
1. `api_key` - Kite API Key
2. `api_secret` - Kite API Secret
3. `user_id` - Kite User ID
4. `password` - Kite Login Password
5. `totp_secret` - TOTP Secret

**Error Message**: "All Kite credentials are required"  
**Test Coverage**: ✓ Rejects missing any of the 5 fields

---

## Error Handling Block 5: Add Account - Try-Catch-Finally

**Location**: `src/components/AccountManager.jsx` (lines 50-69)  
**Function**: `handleAddAccount(e)`  
**Type**: Async operation with error handling and state cleanup

```javascript
      try {
        await api.kiteAddAccount(clientId, formData)

        // Reset form and reload accounts
        setFormData({
          name: '',
          owner: '',
          api_key: '',
          api_secret: '',
          user_id: '',
          password: '',
          totp_secret: '',
        })
        setShowForm(false)
        await loadAccounts()
        onAccountAdded?.()
      } catch (err) {
        setError(err.message)  // BLOCK 5 - Error handling
      } finally {
        setLoading(false)      // Always reset loading
      }
```

**Characteristics**:
- Wraps API call and related operations
- Catches and displays error message
- Clears form on success
- Reloads account list
- Calls callback on success
- `finally` block guarantees loading state reset
- Prevents orphaned loading state

**Success Flow**:
1. API call succeeds
2. Form cleared
3. Form hidden
4. Accounts reloaded
5. Callback invoked

**Error Flow**:
1. API call fails
2. Error message extracted and displayed
3. Form remains visible for retry
4. User can correct and retry

**Network Handling**:
- Network errors caught same way as API errors
- Loading state reset by `finally` block
- Button re-enabled for retry

**Test Coverage**: ✓ API errors, network errors, loading state recovery

---

## Error Handling Block 6: Delete Account - Error Clear and Catch

**Location**: `src/components/AccountManager.jsx` (lines 72-83)  
**Function**: `handleDeleteAccount(accountId)`  
**Type**: Confirmation dialog with error handling

```javascript
async function handleDeleteAccount(accountId) {
  if (!confirm('Delete this account? This cannot be undone.')) {
    return
  }
  try {
    setError('')  // BLOCK 6A - Clear error
    await api.kiteDeleteAccount(clientId, accountId)
    await loadAccounts()
  } catch (err) {
    setError(err.message)  // BLOCK 6B - Error handling
  }
}
```

**Characteristics**:
- Requires user confirmation first
- Clears previous error before operation
- No loading state or finally block
- Error message displayed to user
- Account list reloaded on success

**Confirmation Message**: "Delete this account? This cannot be undone."  
**Test Coverage**: ✓ Error display, cancellation handling

---

## Error Handling Block 7: Sync Account - Error Clear, Try-Catch-Finally

**Location**: `src/components/AccountManager.jsx` (lines 85-101)  
**Function**: `handleSyncAccount(accountId)`  
**Type**: Full async operation with cleanup

```javascript
async function handleSyncAccount(accountId) {
  try {
    setError('')  // BLOCK 7A - Clear error
    setLoading(true)
    const result = await api.kiteSyncAccount(clientId, accountId)
    const msg = result.from_cache
      ? `✓ Synced from cache (${result.message})`
      : `✓ Synced ${result.imported} trades`
    setError(msg)  // Display success as message
    await loadAccounts()
    setTimeout(() => setError(''), 3000)  // Auto-clear after 3 seconds
  } catch (err) {
    setError(`Error syncing: ${err.message}`)  // BLOCK 7B - Error handling
  } finally {
    setLoading(false)  // BLOCK 7C - Always reset loading
  }
}
```

**Characteristics**:
- Complex success/error handling
- Shows success message with checkmark (✓)
- Auto-clears success message after 3 seconds
- Displays error with "Error syncing:" prefix
- Reloads accounts on success
- Full loading state management
- `finally` block guarantees state cleanup

**Success Messages**:
- From cache: `✓ Synced from cache (message)`
- From API: `✓ Synced N trades`

**Error Message Prefix**: "Error syncing: "  
**Auto-clear Timeout**: 3 seconds (success only)

**Test Coverage**: ✓ API errors, loading state, auto-clear, message formatting

---

## Error Handling Block 8: Error Display and Success/Error Styling

**Location**: `src/components/AccountManager.jsx` (lines 115-119)  
**Component**: Error message rendering  
**Type**: Conditional rendering with CSS class toggle

```javascript
      {error && (
        <div className={`error-box ${error.startsWith('✓') ? 'success' : 'error'}`}>
          {error}
        </div>
      )}
```

**Characteristics**:
- Only renders when error state has value
- Detects success messages by checkmark (✓)
- Applies different CSS classes for styling
- Both error and success messages use same div
- Can be styled differently with CSS

**Conditional Classes**:
- `error-box success` - For messages starting with ✓
- `error-box error` - For actual error messages

**Test Coverage**: ✓ Message display, success/error differentiation

---

## Error Handling Summary Table

| Block | Function | Type | Line(s) | Key Feature |
|-------|----------|------|---------|-------------|
| 1 | `loadAccounts` | Silent Catch | 28-30 | Console logging only |
| 2 | `handleAddAccount` | Error Clear | 36 | Clears stale errors |
| 3 | `handleAddAccount` | Name Validation | 39-43 | Rejects empty names |
| 4 | `handleAddAccount` | Credentials Validation | 44-48 | Validates 5 fields |
| 5 | `handleAddAccount` | Try-Catch-Finally | 50-69 | Full async handling |
| 6 | `handleDeleteAccount` | Error Clear + Catch | 77, 81 | Confirmation dialog |
| 7 | `handleSyncAccount` | Try-Catch-Finally | 87-100 | Loading + success/error |
| 8 | Render | Conditional Display | 115-119 | Error/success styling |

---

## Error Propagation Path

```
User Submits Form
    ↓
Block 2: Clear Previous Error (setError(''))
    ↓
Block 3: Validate Name
├─ FAIL → Show Error (Block 3) → Stop
└─ PASS ↓
Block 4: Validate Credentials
├─ FAIL → Show Error (Block 4) → Stop
└─ PASS ↓
Block 5: Try-Catch-Finally
├─ Success Path:
│   ├─ Clear Form
│   ├─ Hide Form
│   ├─ Reload Accounts (Block 1)
│   └─ Call Callback
├─ Error Path:
│   └─ Show Error Message
└─ Finally:
    └─ Reset Loading State
        ↓
Block 8: Render Error Message in UI
```

---

## Critical Design Decisions

1. **Finally Block Usage**: Guarantees loading state reset even if error occurs
2. **Error Clearing**: Each new action starts fresh, preventing stale messages
3. **Validation Before API**: Reduces unnecessary network requests
4. **Silent Load Failure**: Allows app to function even if initial load fails
5. **Confirmation Before Delete**: Prevents accidental account deletion
6. **Auto-clear Success**: Prevents success message from staying permanently
7. **Message Prefixes**: "Error syncing: " helps users identify error source
8. **CSS Class Toggling**: Allows different styling for errors vs success

---

## Testing Recommendations

### Manual Testing

1. **Test Block 3**: Submit form with empty account name
2. **Test Block 4**: Submit form with each credential field empty
3. **Test Block 5**: Submit with valid data, observe success and reload
4. **Test Block 5 Error**: Mock API error, verify error display and retry works
5. **Test Block 6**: Click delete, verify confirmation, test error case
6. **Test Block 7**: Click sync, verify success message auto-clears
7. **Test Block 2, 7A**: Verify error cleared when retrying after failure
8. **Test Block 1**: Disconnect network, verify app still loads empty state

### Automated Testing

- Validate error message text matches expected strings
- Verify button disabled state during loading
- Verify form cleared after successful submission
- Verify error state cleared on new attempts
- Verify finally block executes even on error
- Verify API not called when validation fails

