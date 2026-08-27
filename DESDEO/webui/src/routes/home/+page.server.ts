import { fail, superValidate } from "sveltekit-superforms";
import { zod4 } from "sveltekit-superforms/adapters";
import { loginLoginPost } from "$lib/gen/endpoints/DESDEOFastAPI";
import type { BodyLoginLoginPost } from '$lib/gen/endpoints/DESDEOFastAPI';
import { redirect, type Actions } from "@sveltejs/kit";
import { dev } from "$app/environment";
import { loginSchema } from "./loginSchema";


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

export const load = async ({ cookies }) => {
    const form = await superValidate(zod4(loginSchema));

    if (!cookies.get('refresh_token')) {
        // If developer no-auth mode is enabled, skip the blocking backend POST
        // and redirect to the dashboard. API endpoints rely on the DESDEO_NO_AUTH
        // fallback in the backend, so cookies/tokens are not required for dev.
        if (process.env.DESDEO_NO_AUTH) {
            throw redirect(303, '/dashboard');
        }

        const guestLoggedIn = await loginAsGuest(cookies);
        if (guestLoggedIn) {
            throw redirect(303, '/dashboard');
        }
    }

    return { form };
}

export const actions: Actions = {
    login: async ({request, cookies}) => {

        const form = await superValidate(request, zod4(loginSchema));

        if (!form.valid) {
            return fail(400, { form });
        }

        const body: BodyLoginLoginPost = {
            username: form.data.username,
            password: form.data.password,
            scope: ''
        }

        const response = await loginLoginPost(body);

        if (response.status != 200){
            if (response.status === 401) {
                form.message = "Invalid username or password";
            } else if (response.status >= 500) {
                form.message = "Server unavailable";
            } else {
                form.message = "Login failed. Please try again.";
            }
            return fail(response.status, {form});
        }

        cookies.set("access_token", response.data.access_token, {httpOnly: true, secure: !dev, sameSite: "lax", path: '/'});
        cookies.set("refresh_token", response.data.refresh_token, {httpOnly: true, secure: !dev, sameSite: "lax", path: '/'});

        throw redirect(303, '/dashboard');
    },
};
