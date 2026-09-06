import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AccountManager } from '../AccountManager'
import * as apiModule from '../../api'
import '@testing-library/jest-dom'

// Mock the api module
jest.mock('../../api')

describe('AccountManager - Error Handling Integration', () => {
  const mockClientId = 'test-client-123'

  beforeEach(() => {
    jest.clearAllMocks()
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // ERROR PATH 1: Missing Account Name Validation
  // ═══════════════════════════════════════════════════════════════════════════════
  describe('Error Path 1: Missing Account Name Validation', () => {
    test('should show validation error when account name is empty', async () => {
      const mockOnAccountAdded = jest.fn()
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={mockOnAccountAdded}
        />
      )

      // Open the form
      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      // Leave name empty and try to submit
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)
      const apiSecretInputs = screen.getAllByDisplayValue('')
      const userIdInput = screen.getByPlaceholderText('e.g., QPJ806')
      const passwordInput = screen.getByPlaceholderText(/Kite login password/i)
      const totpSecretInput = screen.getByPlaceholderText(/From Kite Security Settings/i)

      await userEvent.type(apiKeyInput, 'test-api-key')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret')
      await userEvent.type(userIdInput, 'test-user-id')
      await userEvent.type(passwordInput, 'test-password')
      await userEvent.type(totpSecretInput, 'test-totp')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      // Verify error message appears
      await waitFor(() => {
        expect(screen.getByText('Account name is required')).toBeInTheDocument()
      })

      // Verify API was not called
      expect(apiModule.api.kiteAddAccount).not.toHaveBeenCalled()
    })

    test('should show validation error when account name is only whitespace', async () => {
      const mockOnAccountAdded = jest.fn()
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={mockOnAccountAdded}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)

      await userEvent.type(nameInput, '   ')
      await userEvent.type(apiKeyInput, 'test-api-key')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('Account name is required')).toBeInTheDocument()
      })
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // ERROR PATH 2: Missing Kite Credentials Validation
  // ═══════════════════════════════════════════════════════════════════════════════
  describe('Error Path 2: Missing Kite Credentials Validation', () => {
    test('should show validation error when API key is missing', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      await userEvent.type(nameInput, 'Test Account')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('All Kite credentials are required')).toBeInTheDocument()
      })
      expect(apiModule.api.kiteAddAccount).not.toHaveBeenCalled()
    })

    test('should show validation error when API secret is missing', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)

      await userEvent.type(nameInput, 'Test Account')
      await userEvent.type(apiKeyInput, 'test-api-key')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('All Kite credentials are required')).toBeInTheDocument()
      })
      expect(apiModule.api.kiteAddAccount).not.toHaveBeenCalled()
    })

    test('should show validation error when user_id is missing', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)
      const apiSecretInputs = screen.getAllByDisplayValue('')
      const passwordInput = screen.getByPlaceholderText(/Kite login password/i)

      await userEvent.type(nameInput, 'Test Account')
      await userEvent.type(apiKeyInput, 'test-api-key')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret')
      await userEvent.type(passwordInput, 'test-password')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('All Kite credentials are required')).toBeInTheDocument()
      })
    })

    test('should show validation error when password is missing', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)
      const apiSecretInputs = screen.getAllByDisplayValue('')
      const userIdInput = screen.getByPlaceholderText('e.g., QPJ806')

      await userEvent.type(nameInput, 'Test Account')
      await userEvent.type(apiKeyInput, 'test-api-key')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret')
      await userEvent.type(userIdInput, 'test-user-id')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('All Kite credentials are required')).toBeInTheDocument()
      })
    })

    test('should show validation error when TOTP secret is missing', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)
      const apiSecretInputs = screen.getAllByDisplayValue('')
      const userIdInput = screen.getByPlaceholderText('e.g., QPJ806')
      const passwordInput = screen.getByPlaceholderText(/Kite login password/i)

      await userEvent.type(nameInput, 'Test Account')
      await userEvent.type(apiKeyInput, 'test-api-key')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret')
      await userEvent.type(userIdInput, 'test-user-id')
      await userEvent.type(passwordInput, 'test-password')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('All Kite credentials are required')).toBeInTheDocument()
      })
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // ERROR PATH 3: API Error Response on Account Add
  // ═══════════════════════════════════════════════════════════════════════════════
  describe('Error Path 3: API Error Response on Account Add', () => {
    test('should display API error message when kiteAddAccount fails', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })
      const apiError = new Error('Invalid API credentials')
      apiModule.api.kiteAddAccount.mockRejectedValueOnce(apiError)

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)
      const apiSecretInputs = screen.getAllByDisplayValue('')
      const userIdInput = screen.getByPlaceholderText('e.g., QPJ806')
      const passwordInput = screen.getByPlaceholderText(/Kite login password/i)
      const totpSecretInput = screen.getByPlaceholderText(/From Kite Security Settings/i)

      await userEvent.type(nameInput, 'Test Account')
      await userEvent.type(apiKeyInput, 'test-api-key')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret')
      await userEvent.type(userIdInput, 'test-user-id')
      await userEvent.type(passwordInput, 'test-password')
      await userEvent.type(totpSecretInput, 'test-totp')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('Invalid API credentials')).toBeInTheDocument()
      })
    })

    test('should handle HTTP 400 error responses', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })
      const httpError = new Error('HTTP 400: Bad Request')
      apiModule.api.kiteAddAccount.mockRejectedValueOnce(httpError)

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)
      const apiSecretInputs = screen.getAllByDisplayValue('')
      const userIdInput = screen.getByPlaceholderText('e.g., QPJ806')
      const passwordInput = screen.getByPlaceholderText(/Kite login password/i)
      const totpSecretInput = screen.getByPlaceholderText(/From Kite Security Settings/i)

      await userEvent.type(nameInput, 'Test Account')
      await userEvent.type(apiKeyInput, 'test-api-key')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret')
      await userEvent.type(userIdInput, 'test-user-id')
      await userEvent.type(passwordInput, 'test-password')
      await userEvent.type(totpSecretInput, 'test-totp')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText(/HTTP 400/)).toBeInTheDocument()
      })
    })

    test('should handle HTTP 401 unauthorized error', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })
      const httpError = new Error('HTTP 401: Unauthorized')
      apiModule.api.kiteAddAccount.mockRejectedValueOnce(httpError)

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)
      const apiSecretInputs = screen.getAllByDisplayValue('')
      const userIdInput = screen.getByPlaceholderText('e.g., QPJ806')
      const passwordInput = screen.getByPlaceholderText(/Kite login password/i)
      const totpSecretInput = screen.getByPlaceholderText(/From Kite Security Settings/i)

      await userEvent.type(nameInput, 'Test Account')
      await userEvent.type(apiKeyInput, 'test-api-key')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret')
      await userEvent.type(userIdInput, 'test-user-id')
      await userEvent.type(passwordInput, 'test-password')
      await userEvent.type(totpSecretInput, 'test-totp')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText(/HTTP 401/)).toBeInTheDocument()
      })
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // ERROR PATH 4: Network Error on Account Add
  // ═══════════════════════════════════════════════════════════════════════════════
  describe('Error Path 4: Network Error on Account Add', () => {
    test('should handle network timeout gracefully', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })
      const networkError = new Error('Network timeout')
      apiModule.api.kiteAddAccount.mockRejectedValueOnce(networkError)

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)
      const apiSecretInputs = screen.getAllByDisplayValue('')
      const userIdInput = screen.getByPlaceholderText('e.g., QPJ806')
      const passwordInput = screen.getByPlaceholderText(/Kite login password/i)
      const totpSecretInput = screen.getByPlaceholderText(/From Kite Security Settings/i)

      await userEvent.type(nameInput, 'Test Account')
      await userEvent.type(apiKeyInput, 'test-api-key')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret')
      await userEvent.type(userIdInput, 'test-user-id')
      await userEvent.type(passwordInput, 'test-password')
      await userEvent.type(totpSecretInput, 'test-totp')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('Network timeout')).toBeInTheDocument()
      })
    })

    test('should reset loading state after network error', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })
      const networkError = new Error('Connection failed')
      apiModule.api.kiteAddAccount.mockRejectedValueOnce(networkError)

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)
      const apiSecretInputs = screen.getAllByDisplayValue('')
      const userIdInput = screen.getByPlaceholderText('e.g., QPJ806')
      const passwordInput = screen.getByPlaceholderText(/Kite login password/i)
      const totpSecretInput = screen.getByPlaceholderText(/From Kite Security Settings/i)

      await userEvent.type(nameInput, 'Test Account')
      await userEvent.type(apiKeyInput, 'test-api-key')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret')
      await userEvent.type(userIdInput, 'test-user-id')
      await userEvent.type(passwordInput, 'test-password')
      await userEvent.type(totpSecretInput, 'test-totp')

      const submitButton = screen.getByRole('button', { name: /Add Account/i })
      expect(submitButton).toHaveTextContent('Add Account')

      fireEvent.click(submitButton)

      // Wait for loading state
      await waitFor(() => {
        expect(submitButton).toHaveTextContent('Adding...')
      })

      // Wait for error and loading state reset
      await waitFor(() => {
        expect(submitButton).toHaveTextContent('Add Account')
        expect(submitButton).not.toBeDisabled()
      })
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // ERROR PATH 5: Delete Account API Error
  // ═══════════════════════════════════════════════════════════════════════════════
  describe('Error Path 5: Delete Account API Error', () => {
    test('should display error when delete account fails', async () => {
      const mockAccounts = [
        {
          id: 'acc-123',
          name: 'Test Account',
          user_name: 'Test User',
          is_active: true,
        },
      ]
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: mockAccounts })
      const deleteError = new Error('Account in use, cannot delete')
      apiModule.api.kiteDeleteAccount.mockRejectedValueOnce(deleteError)

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Test User')).toBeInTheDocument()
      })

      const deleteButton = screen.getByRole('button', { name: '🗑️' })

      // Mock confirm dialog
      window.confirm = jest.fn(() => true)

      fireEvent.click(deleteButton)

      await waitFor(() => {
        expect(screen.getByText('Account in use, cannot delete')).toBeInTheDocument()
      })
    })

    test('should not call delete API if user cancels confirmation', async () => {
      const mockAccounts = [
        {
          id: 'acc-123',
          name: 'Test Account',
          user_name: 'Test User',
          is_active: true,
        },
      ]
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: mockAccounts })

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Test User')).toBeInTheDocument()
      })

      const deleteButton = screen.getByRole('button', { name: '🗑️' })

      // Mock confirm dialog to return false
      window.confirm = jest.fn(() => false)

      fireEvent.click(deleteButton)

      expect(apiModule.api.kiteDeleteAccount).not.toHaveBeenCalled()
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // ERROR PATH 6: Sync Account API Error
  // ═══════════════════════════════════════════════════════════════════════════════
  describe('Error Path 6: Sync Account API Error', () => {
    test('should display error when sync account fails', async () => {
      const mockAccounts = [
        {
          id: 'acc-123',
          name: 'Test Account',
          user_name: 'Test User',
          is_active: true,
        },
      ]
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: mockAccounts })
      const syncError = new Error('Authentication expired')
      apiModule.api.kiteSyncAccount.mockRejectedValueOnce(syncError)

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Test User')).toBeInTheDocument()
      })

      const syncButton = screen.getByRole('button', { name: /🔄 Sync/i })
      fireEvent.click(syncButton)

      await waitFor(() => {
        expect(screen.getByText('Error syncing: Authentication expired')).toBeInTheDocument()
      })
    })

    test('should reset loading state after sync error', async () => {
      const mockAccounts = [
        {
          id: 'acc-123',
          name: 'Test Account',
          user_name: 'Test User',
          is_active: true,
        },
      ]
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: mockAccounts })
      const syncError = new Error('API rate limit exceeded')
      apiModule.api.kiteSyncAccount.mockRejectedValueOnce(syncError)

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Test User')).toBeInTheDocument()
      })

      const syncButton = screen.getByRole('button', { name: /🔄 Sync/i })
      fireEvent.click(syncButton)

      // Sync button should not be disabled after error
      await waitFor(() => {
        expect(syncButton).not.toBeDisabled()
      })
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // ERROR PATH 7: Load Accounts Error
  // ═══════════════════════════════════════════════════════════════════════════════
  describe('Error Path 7: Load Accounts Error (Silent Fail)', () => {
    test('should handle loadAccounts error gracefully (logged but not shown)', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
      const loadError = new Error('Failed to fetch accounts')
      apiModule.api.kiteListAccounts.mockRejectedValueOnce(loadError)

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Error loading accounts:',
          loadError
        )
      })

      // Should show empty state
      expect(screen.getByText('No Kite accounts yet.')).toBeInTheDocument()

      consoleErrorSpy.mockRestore()
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // ERROR PATH 8: Error State Clearing on Retry
  // ═══════════════════════════════════════════════════════════════════════════════
  describe('Error Path 8: Error State Clearing on Retry', () => {
    test('should clear previous error when attempting new action', async () => {
      apiModule.api.kiteListAccounts.mockResolvedValue({ accounts: [] })
      const addError = new Error('Invalid credentials')
      apiModule.api.kiteAddAccount
        .mockRejectedValueOnce(addError)
        .mockResolvedValueOnce({ accounts: [] })

      render(
        <AccountManager
          clientId={mockClientId}
          onAccountAdded={jest.fn()}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(addButton)

      const nameInput = screen.getByPlaceholderText(/e.g., Sumanth Trading/i)
      const apiKeyInput = screen.getByPlaceholderText(/From Kite Console/i)
      const apiSecretInputs = screen.getAllByDisplayValue('')
      const userIdInput = screen.getByPlaceholderText('e.g., QPJ806')
      const passwordInput = screen.getByPlaceholderText(/Kite login password/i)
      const totpSecretInput = screen.getByPlaceholderText(/From Kite Security Settings/i)

      // First attempt - should fail
      await userEvent.type(nameInput, 'Test Account')
      await userEvent.type(apiKeyInput, 'test-api-key')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret')
      await userEvent.type(userIdInput, 'test-user-id')
      await userEvent.type(passwordInput, 'test-password')
      await userEvent.type(totpSecretInput, 'test-totp')

      let submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('Invalid credentials')).toBeInTheDocument()
      })

      // Clear and retry
      await userEvent.clear(nameInput)
      await userEvent.clear(apiKeyInput)
      await userEvent.clear(apiSecretInputs[1])
      await userEvent.clear(userIdInput)
      await userEvent.clear(passwordInput)
      await userEvent.clear(totpSecretInput)

      await userEvent.type(nameInput, 'Test Account 2')
      await userEvent.type(apiKeyInput, 'test-api-key-2')
      await userEvent.type(apiSecretInputs[1], 'test-api-secret-2')
      await userEvent.type(userIdInput, 'test-user-id-2')
      await userEvent.type(passwordInput, 'test-password-2')
      await userEvent.type(totpSecretInput, 'test-totp-2')

      submitButton = screen.getByRole('button', { name: /Add Account/i })
      fireEvent.click(submitButton)

      // Error should be cleared on new attempt
      await waitFor(() => {
        expect(screen.queryByText('Invalid credentials')).not.toBeInTheDocument()
      })

      expect(apiModule.api.kiteAddAccount).toHaveBeenCalledTimes(2)
    })
  })
})
