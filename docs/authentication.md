# Authentication

The browser application uses server-side reference sessions. Authentication credentials are never placed in URLs or browser storage.

## Passwords
Passwords are hashed with Python's built-in scrypt implementation. The stored value contains algorithm parameters, a random salt, and derived key; plaintext passwords are never persisted.

## Sessions
A successful login creates a cryptographically random session token. Only a SHA-256 hash of that token is stored in PostgreSQL. Sessions are bound to a user and organization, expire after the configured session TTL, and can be revoked server-side.

Production uses Host-prefixed cookies with Secure, HttpOnly, SameSite=Strict, and Path=/. Development may disable Secure for local HTTP operation. Authentication tokens are never stored in localStorage or sessionStorage.

## CSRF
State-changing browser requests require an X-CSRF-Token header matching the CSRF cookie and the CSRF value bound to the server-side session. SameSite cookies provide defense in depth.

## Bootstrap
Initial owner creation is disabled unless deployment secrets configure the bootstrap token, email, and password. Bootstrap is one-time: once a user exists, the endpoint cannot create another initial account.

## Logout
Logout revokes the server-side session and clears authentication cookies.

## Standards mapping
The implementation is intended to support selected OWASP ASVS 5.0 session-management controls. It is not a certification or formal security assessment.
