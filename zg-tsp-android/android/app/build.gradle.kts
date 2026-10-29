import java.io.File
import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// ---- 签名配置 ----
// 真实密钥写在 android/key.properties（已 gitignore），本文件不含任何密钥。
// key.properties 不存在时 release 回退到 debug 签名 —— 仅供内部测试，不可上架；
// scripts/build.sh 的 check_android_signing 会在缺失时给出同样的告警。
// 模板见 android/key.properties.example。
val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
val hasReleaseKeystore = keystorePropertiesFile.exists()
if (hasReleaseKeystore) {
    keystoreProperties.load(keystorePropertiesFile.inputStream())
}
// storeFile 的相对路径以 android/ 目录为基准
val keystoreStoreFile: File? = if (hasReleaseKeystore) {
    val storeFilePath = keystoreProperties.getProperty("storeFile")
    if (storeFilePath != null) rootProject.file(storeFilePath) else null
} else {
    null
}

android {
    namespace = "com.zgtsp.zg_tsp_android"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.zgtsp.zg_tsp_android"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // ---- 渠道配置（由 scripts/build.sh 生成）----
    buildFeatures {
        // resValue("string", "app_name", ...) 需要显式开启（AGP 9.x 默认关闭）
        resValues = true
    }
    flavorDimensions += "channel"
    productFlavors {
        create("dev") {
            dimension = "channel"
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
            resValue("string", "app_name", "zg-tsp-dev")
        }
        create("prod") {
            dimension = "channel"
            versionNameSuffix = "-prod"
            resValue("string", "app_name", "zg-tsp")
        }
    }
    signingConfigs {
        if (hasReleaseKeystore) {
            create("release") {
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
                storeFile = keystoreStoreFile
                storePassword = keystoreProperties.getProperty("storePassword")
            }
        }
    }
    buildTypes {
        release {
            // 有 key.properties 就用正式签名；否则退回 debug 签名（不可上架）
            signingConfig = if (hasReleaseKeystore) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
