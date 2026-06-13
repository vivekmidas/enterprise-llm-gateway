import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get('code');
  const state = searchParams.get('state'); // Expected format: "workflow_id|node_id"

  if (!code || !state) {
    return NextResponse.json({ error: 'Missing code or state' }, { status: 400 });
  }

  // Expected state format: "workflow_id|node_id|client_id|client_secret"
  const parts = state.split('|');
  if (parts.length < 4) {
    return NextResponse.json({ error: 'Invalid state context' }, { status: 400 });
  }
  const [workflow_id, node_id, client_id, client_secret] = parts;

  try {
    // 1. Exchange the authorization code for tokens
    const response = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        code,
        client_id,
        client_secret,
        redirect_uri: `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/callback`,
        grant_type: 'authorization_code',
      }),
    });

    const tokens = await response.json();

    if (!response.ok) {
      throw new Error(tokens.error_description || tokens.error || 'Failed to exchange token');
    }

    // 2. Send tokens to the backend to be stored in workflow_node_properties
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
    const backendRes = await fetch(`${backendUrl}/webhooks/email/refresh-token`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflow_id,
        node_id,
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token,
      }),
    });

    if (!backendRes.ok) {
      const errorMsg = await backendRes.text();
      throw new Error(`Backend storage failed: ${errorMsg}`);
    }

    // 3. Return HTML to notify the main window and close the popup
    return new NextResponse(
      `<html>
        <body>
          <script>
            if (window.opener) {
              window.opener.postMessage({ type: 'AUTH_SUCCESS', workflow_id: '${workflow_id}', node_id: '${node_id}' }, '*');
            }
            window.close();
          </script>
        </body>
      </html>`,
      { headers: { 'Content-Type': 'text/html' } }
    );
  } catch (error: any) {
    console.error('OAuth Callback Error:', error);
    return NextResponse.json({ error: error.message || 'Authentication failed' }, { status: 500 });
  }
}