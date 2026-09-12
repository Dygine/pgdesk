package in.kredo.pgguru;

import android.os.Bundle;
import android.webkit.CookieManager;

import com.getcapacitor.BridgeActivity;

/**
 * PGuru Android host.
 *
 * WHY THIS FILE IS NOT EMPTY
 * --------------------------
 * PGuru keeps its refresh token in an HttpOnly, Secure, SameSite=None cookie
 * scoped to /api/v1/auth. That is the right design: JavaScript cannot read the
 * long-lived credential, so an XSS cannot steal it.
 *
 * Inside Capacitor the WebView is served from https://localhost, while the API
 * lives on a different host. Every API call is therefore *cross-site*, and the
 * refresh cookie is a third-party cookie.
 *
 * Android's WebView refuses third-party cookies by default, and Capacitor's
 * Bridge does not change that - only the Cordova compatibility layer calls
 * setAcceptThirdPartyCookies, and a plain Capacitor app never goes through it.
 *
 * Without the call below the symptom is subtle and bad: login works (the access
 * token arrives in the response body), then the session dies ~30 minutes later
 * and on every cold start, because POST /auth/refresh arrives with no cookie.
 *
 * The alternative - EXPOSE_REFRESH_TOKEN_IN_BODY=true plus secure storage -
 * would mean turning off a guard that app/core/config.py deliberately refuses
 * in production, and would put the long-lived token somewhere script can read.
 * A few lines here is the cheaper and safer trade.
 */
public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        // getBridge().getWebView() is only valid once super.onCreate has run.
        cookieManager.setAcceptThirdPartyCookies(getBridge().getWebView(), true);
    }
}
