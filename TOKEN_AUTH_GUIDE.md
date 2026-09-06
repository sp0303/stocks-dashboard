# Token-Based Authentication Guide
**For Kite Integration Without CAPTCHA**

---

## 🎯 The Problem

Kite requires **CAPTCHA on every new programmatic login**. This blocks automated credential-based authentication.

## ✅ The Solution

Use **Token-Based Authentication**: Manually log in once via browser, capture the access token, and use it in your app. No CAPTCHA needed for subsequent API calls!

---

## 📝 Step-by-Step Instructions

### Step 1: Open Kite Website
Go to: https://kite.zerodha.com

### Step 2: Log In Manually
1. Enter User ID: **QPJ806**
2. Click "Login"
3. Solve CAPTCHA (one time only)
4. Enter Password: **Sumanth@27**
5. Complete 2FA with TOTP

After successful login, you'll see the Kite dashboard.

### Step 3: Capture Access Token
1. **Open Developer Tools** (F12 or Cmd+Option+I on Mac)
2. Go to **Network** tab
3. Click on any API request (e.g., any GET request)
4. Look for **Authorization** header in Request Headers
5. Copy the value that looks like: `Bearer <long_token_string>`
6. The token is everything after "Bearer "

**Example:**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Copy only the token part (without "Bearer ")

### Step 4: Add Account in Dashboard

Now go back to your Portfolio dashboard at http://localhost:5173

1. Click **"+ Add Account"** button
2. Select **"🔗 Access Token"** (default/recommended)
3. Fill in:
   - **Account Name**: e.g., "Sumanth Trading"
   - **Owner Name**: e.g., "Sumanth Billa"  
   - **API Key**: `qjrz8qtbxcy9qcuq`
   - **Access Token**: (paste from Step 3)
4. Click **Submit**

✅ Account added! No CAPTCHA needed!

---

## 🔄 How It Works

### First Time (Manual)
```
User logs in via browser → Captures token → Stores in app
```

### Every Time After (Automatic)
```
App uses stored token → Makes API calls → No CAPTCHA!
```

---

## ⏱️ When Token Expires

Access tokens typically expire after **~30 days** of inactivity.

**When it expires:**
1. User logs in manually again
2. Captures new token
3. Updates in app settings
4. Continue using app

---

## 🔒 Security Notes

1. **Access Token** = Equivalent to a logged-in session
2. Keep it private (don't share in emails/messages)
3. Similar to a password - if someone gets it, they can access your account
4. More secure than storing actual password + TOTP secret
5. Can be revoked by logging out from Kite

---

## 📚 API Details

### Backend Endpoint

```bash
POST /api/clients/{client_id}/broker/kite/accounts
```

**Request Body (Token-Based):**
```json
{
  "name": "Sumanth Trading",
  "owner": "Sumanth Billa",
  "api_key": "qjrz8qtbxcy9qcuq",
  "access_token": "<your_token_here>"
}
```

**Request Body (Credentials-Based - Fallback):**
```json
{
  "name": "Sumanth Trading",
  "owner": "Sumanth Billa",
  "api_key": "qjrz8qtbxcy9qcuq",
  "api_secret": "0up53rdbf0hyjw48pnb1s03j6ybvjuiv",
  "user_id": "QPJ806",
  "password": "Sumanth@27",
  "totp_secret": "Y54RV3LKV4LBR6DEAGT6DZHN4BL3LUUH"
}
```

**Response:**
```json
{
  "data": {
    "account": {
      "id": "account_123",
      "name": "Sumanth Trading",
      "user_name": "Sumanth Billa",
      "email": "sumanth@example.com",
      "phone": "+91-98765-43210",
      "account_type": "margin"
    }
  }
}
```

---

## 🧪 Testing

### Quick Test Command
```bash
# Test if token is valid
curl -H "Authorization: Bearer <your_token>" \
  https://api.kite.trade/profile
```

If it returns user profile → token is valid ✅

---

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| "Invalid access token" | Token expired or incorrect - recapture from browser |
| "Token not found in header" | Make sure you copied "Bearer value" correctly |
| "401 Unauthorized" | Token is expired - log in to Kite again and get new token |
| Can't find Authorization header | Try clicking a different API request in Network tab |

---

## 🎯 Benefits of Token-Based Auth

✅ **No CAPTCHA** - Solve it once, use forever (until token expires)  
✅ **Safer** - Don't store passwords in .env file  
✅ **Simpler** - Less credential information needed  
✅ **Works 24/7** - Token stays valid for days/weeks  
✅ **Flexible** - Easy to refresh when needed  

---

## 🚀 Next Steps

1. Log in to Kite manually
2. Capture access token
3. Add account in dashboard using token
4. Test adding 2-3 accounts
5. Verify all features work

---

**Created**: 2026-09-05  
**Status**: ✅ Token-Based Auth Enabled  
**Recommendation**: Use token method (skip credentials method)

