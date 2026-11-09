# Security Policy

[English](SECURITY.md) | [简体中文](../docs/SECURITY_zh.md)

Thank you for helping us keep **NTE Auto-Fishing** secure. We take security seriously and appreciate your efforts to responsibly disclose any vulnerabilities.

This document outlines our security support lifecycle, threat model, and the process for reporting potential security issues.

---

## Supported Versions

We actively support and patch security issues for the following versions:

| Version | Supported | Notes |
| :--- | :--- | :--- |
| **Latest Stable Release** | :white_check_mark: Yes | Only the most recent stable release is actively supported. |
| **Older Releases** | :x: No | Please upgrade to the latest release to receive updates. |

We recommend always running the latest version available on the [Releases](https://github.com/vnoiram/NTE-auto-fish/releases) page to ensure you have the latest performance, usability, and security improvements.

---

## Threat Model & Security Context

Because **NTE Auto-Fishing** is a local automation tool, there are specific security boundaries to keep in mind:

### 1. Elevated Privileges (Administrator Mode)
- **Context**: On Windows, the bot requires Administrator privileges to simulate inputs successfully (via `PyDirectInput` and `ctypes.windll`) so that they are registered by elevated game windows.
- **Risk**: Running *any* software as Administrator grants it full access to your operating system. A vulnerability in the bot's input processing, GUI parsing, or dependencies could potentially be exploited for local privilege escalation (LPE).
- **Mitigation**: We keep our dependencies minimal, avoid parsing untrusted external inputs, and run fully locally. Always verify that you download official builds directly from [vnoiram/NTE-auto-fish](https://github.com/vnoiram/NTE-auto-fish).

### 2. Fully Local Operation (Air-Gapped)
- **Context**: The core bot ([main.py](../main.py) and the DearPyGui interface in [gui/](../gui/)) executes fully on your local machine.
- **Privacy**: The bot does **not** collect telemetry, capture screen buffers to send online, or communicate with any external web servers.
- **Exceptions**: Standard package managers (`pip`) or Git operations are only used during installation and development updates.

### 3. Anti-Cheat & Account Safety
- **Context**: While this is a "security" policy, user safety is paramount. 
- **Disclaimer**: Using automation tools, bots, or assistants may violate the game's Terms of Service (ToS) and could result in account suspension or bans.
- **Mitigation**: The bot employs customizable, humanized mouse and keyboard behaviors, and operates purely on non-invasive computer vision (OpenCV) rather than reading/writing game memory. However, you use this software at your own risk.

---

## Reporting a Vulnerability

> [!IMPORTANT]
> **Do NOT open a public issue** for security vulnerabilities. Publicly disclosing a security vulnerability makes your system and other users' systems vulnerable before a patch can be developed.

If you believe you have discovered a security vulnerability in this project, please follow the steps below:

1. **Submit a Private Vulnerability Report**:
   - Go to the **Security** tab of this repository on GitHub.
   - Click on **Advisories** in the sidebar.
   - Click **Report a vulnerability** to submit a private draft advisory.
   - Provide a detailed description of the vulnerability, including step-by-step reproduction instructions, affected platform/OS details, and a working proof-of-concept (PoC) if possible.

2. **Alternative Contact**:
   - If Private Vulnerability Reporting is unavailable, you can open an issue requesting a secure contact method, or submit details via a secure, private communication channel with the maintainer **vnoiram** on GitHub.

### Our Response Process

- **Acknowledgment**: We will acknowledge receipt of your report within **48 hours** and verify the vulnerability.
- **Investigation**: We will work closely with you to understand and reproduce the issue.
- **Remediation**: Once verified, we will aim to publish a patched release within **7–14 days**, depending on the complexity of the fix.
- **Attribution**: With your permission, we will gladly credit you for the discovery in our release notes and change logs.
