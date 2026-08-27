import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

async function loginAsGuest(cookies: any) {
  const response = await fetch('http://localhost:8000/login', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: 'guest', password: 'guest', scope: '' }),
  });

  if (!response.ok) {
    return false;
  }

  const data = await response.json();
  cookies.set('access_token', data.access_token, { httpOnly: true, secure: false, sameSite: 'lax', path: '/' });
  cookies.set('refresh_token', data.refresh_token, { httpOnly: true, secure: false, sameSite: 'lax', path: '/' });
  return true;
}

export const load: PageServerLoad = async ({ cookies }) => {
  const refreshToken = cookies.get('refresh_token');
  if (!refreshToken) {
    const ok = await loginAsGuest(cookies);
    if (!ok) {
      throw redirect(307, '/home');
    }
  }
  return {};
};