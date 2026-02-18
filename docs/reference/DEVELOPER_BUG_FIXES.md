# Slack Message to Developers - Bug Fixes Required

---

**Subject: Bug Fixes & Configuration Corrections Needed - No New Features**

Hi team,

I've done a detailed review of the app and found several bugs and configuration issues that need to be fixed. These are not new features - they are corrections to existing functionality that should have been working properly.

I've listed each issue below with **exact file locations and line numbers** so there's no confusion about what needs to be changed.

---

## 🔴 BUG #1: Typo - "Setting" should be "Settings"

**File:** `lib/view/SettingScreen/settings.dart`
**Line:** 21

**Current code:**
```dart
title: const Text(
  "Setting",
```

**Change to:**
```dart
title: const Text(
  "Settings",
```

**Time to fix:** 1 minute

---

## 🔴 BUG #2: "Ask Your HVAC Pro" in drawer does nothing when tapped

**File:** `lib/view/Drawer/CustomDrawer.dart`
**Lines:** 55-57

**Current code:**
```dart
_tileWithIcon(
  'assets/icons/hvca.svg',
  "Ask Your HVAC Pro",
),
```

**Problem:** There is no `onTap` handler. When user taps this, nothing happens.

**Fix:** Wrap it in a `SpringWidget` with navigation, like this:
```dart
SpringWidget(
  onTap: () {
    chatController.resetThread();
    chatController.messagesList.clear();
    Get.back(); // Close drawer
  },
  child: _tileWithIcon(
    'assets/icons/hvca.svg',
    "Ask Your HVAC Pro",
  ),
),
```

**Time to fix:** 5 minutes

---

## 🔴 BUG #3: "Upgrade to Plus" shows for users who already have a subscription

**File:** `lib/view/Drawer/CustomDrawer.dart`
**Lines:** 58-61

**Current code:**
```dart
SpringWidget(
    onTap: () {
      Get.toNamed(RoutesName.subscriptionview);
    },
    child: _tileWithIcon(
        'assets/icons/crowns.svg', "Upgrade to Plus")),
```

**Problem:** This shows for ALL users, even those who already paid for a subscription.

**Fix:** Wrap it in an `Obx` with a condition to check subscription status:
```dart
Obx(() => LocalDataStorage.isSubscribed.value == false
  ? SpringWidget(
      onTap: () {
        Get.toNamed(RoutesName.subscriptionview);
      },
      child: _tileWithIcon(
          'assets/icons/crowns.svg', "Upgrade to Plus"))
  : SizedBox.shrink(),
),
```

(Adjust the variable name `isSubscribed` to whatever you're using to track subscription status)

**Time to fix:** 5 minutes

---

## 🔴 BUG #4: Missing "New Chat" button on Android

The drawer on iOS has a "New Chat" button but Android does not. This needs to be added to `CustomDrawer.dart` so both platforms have the same functionality.

**File:** `lib/view/Drawer/CustomDrawer.dart`

**Fix:** Add a "New Chat" button near the top of the drawer (after the search bar, before "Ask Your HVAC Pro"):
```dart
SpringWidget(
  onTap: () {
    chatController.resetThread();
    chatController.messagesList.clear();
    Get.back(); // Close drawer
    // Navigate to home/chat screen if needed
  },
  child: _tileWithIcon(
    'assets/icons/add.svg', // or whatever icon you have
    "New Chat",
  ),
),
```

**Time to fix:** 5 minutes

---

## 🟡 CONFIGURATION #5: Voice silence detection too slow

**File:** `lib/view/home_page/voiceScreen/voiceChatScreen.dart`
**Line:** 255

**Current code:**
```dart
pauseFor: Duration(seconds: 4),
```

**Problem:** The app waits 4+ seconds after the user stops talking before processing. This makes the voice experience feel slow and unresponsive. Industry standard for conversational AI is 1-2 seconds.

**Change to:**
```dart
pauseFor: Duration(seconds: 2),
```

**Time to fix:** 1 minute

---

## 🟡 CONFIGURATION #6: ElevenLabs Voice Settings Need Optimization

**File:** `lib/helper/constants.dart` (or wherever ElevenLabs settings are defined)

Please make these changes to the ElevenLabs configuration:

| Setting | Current Value | Change To | Why |
|---------|---------------|-----------|-----|
| Model | `eleven_turbo_v2_5` | `eleven_flash_v2_5` | Faster response time |
| Stability | `0.5` | `0.7` | Fixes audio stutter/glitching |
| Similarity Boost | `0.8` | `0.9` | Better voice match to original |

If these settings are in `elevenlabs_service.dart` in the API request body, find the `voice_settings` object and update it:

```dart
'voice_settings': {
  'stability': 0.7,           // was 0.5
  'similarity_boost': 0.9,    // was 0.8
  'style': 0.0,
  'use_speaker_boost': true,
}
```

And change the model_id:
```dart
'model_id': 'eleven_flash_v2_5',  // was eleven_turbo_v2_5
```

**Time to fix:** 5 minutes

---

## Summary

| Issue | Type | Time to Fix |
|-------|------|-------------|
| "Setting" typo | Bug | 1 min |
| "Ask Your HVAC Pro" not clickable | Bug | 5 min |
| "Upgrade to Plus" showing for subscribers | Bug | 5 min |
| Missing "New Chat" on Android | Bug | 5 min |
| Voice silence detection too slow | Config | 1 min |
| ElevenLabs voice settings | Config | 5 min |

**Total estimated time: ~22 minutes**

---

These are all bug fixes and configuration corrections - not new feature requests. I would expect these to be addressed at no additional charge as they represent issues that should have been caught during development and QA.

Please let me know when you can have these completed.

Thanks,
Tom

