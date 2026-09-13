# ---------------------------------------------------------------------------
# ProGuard / R8 rules.
#
# `minifyEnabled true` is set for release in build.gradle. That is fine for the
# Java in this app, which is almost nothing - but Capacitor is not ordinary
# Java. It finds plugins at runtime by reading the @CapacitorPlugin annotation
# off the class, and R8 strips runtime annotation metadata by default.
#
# The symptom when these rules are missing is not a build failure. The APK
# compiles, installs and launches. It dies later, natively, with:
#
#   FATAL EXCEPTION: CapacitorPlugins
#   java.lang.NullPointerException
#     at com.getcapacitor.Plugin.getPermissionStates
#     at com.capacitorjs.plugins.pushnotifications.PushNotificationsPlugin
#         .checkPermissions
#
# because the annotation it wants to read is no longer there. A native crash on
# the plugin thread cannot be caught from JavaScript - the process is gone.
#
# Debug builds are not minified, which is why this never appears until the
# release build reaches a phone.
# ---------------------------------------------------------------------------


# --- keep stack traces readable -------------------------------------------
# Without these, every future crash report is `r8-map-id-7fec3de08ec1...`
# instead of a file and line number, and diagnosing anything means matching
# mapping.txt by hand against a build nobody kept. The cost is a few KB.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile


# --- Capacitor -------------------------------------------------------------
# Annotations are load-bearing here, not documentation. @CapacitorPlugin,
# @PluginMethod, @PermissionCallback and @ActivityCallback are all read
# reflectively at runtime, so the metadata has to survive shrinking.
-keepattributes *Annotation*
-keepattributes Signature
-keepattributes InnerClasses
-keepattributes EnclosingMethod

-keep class com.getcapacitor.** { *; }
-keep interface com.getcapacitor.** { *; }

# Every plugin class, plus the methods the bridge calls by name. Keeping the
# constructor matters too: plugins are instantiated reflectively, and a
# constructor R8 believes is unused is a constructor R8 removes.
-keep @com.getcapacitor.annotation.CapacitorPlugin public class * {
    @com.getcapacitor.annotation.PermissionCallback <methods>;
    @com.getcapacitor.annotation.ActivityCallback <methods>;
    @com.getcapacitor.PluginMethod public <methods>;
    public <init>(...);
}

# The official plugins (push-notifications, geolocation, preferences,
# status-bar, keyboard, app) and the Cordova compatibility layer.
-keep class com.capacitorjs.** { *; }
-keep class org.apache.cordova.** { *; }


# --- Firebase Cloud Messaging ---------------------------------------------
# FCM resolves its service and receiver classes from the merged manifest by
# name. A renamed class is a class the manifest can no longer point at, and
# the failure mode is silent: notifications simply never arrive.
-keep class com.google.firebase.** { *; }
-keep class com.google.android.gms.** { *; }
-dontwarn com.google.firebase.**
-dontwarn com.google.android.gms.**


# --- ML Kit barcode scanning ----------------------------------------------
# Same reasoning: native model bindings resolved by name.
-keep class com.google.mlkit.** { *; }
-dontwarn com.google.mlkit.**


# --- WebView JavaScript bridge --------------------------------------------
# @JavascriptInterface methods are called from JavaScript by their original
# name. Renaming one breaks the call with no error on either side.
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
