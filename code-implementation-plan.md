# ESP32 Auto Sync Implementation Plan

## Overview

This plan outlines an approach to automate the process of identifying and uploading modified files in the `device/` directory to an ESP32 device, eliminating the need for manual file selection.

## Current Workflow

Currently, you manually identify which files have changed and upload them using a comma-separated list:

```bash
./run upload x,y,z
```

## Proposed Solution

Add a new `sync` command to the `run` script that automatically:

1. Detects which files in the `device/` directory have been modified since the last upload
2. Uploads only those modified files to the ESP32
3. Tracks when files were last synced for future comparison

```mermaid
flowchart TD
    A[Start: run sync] --> B{Check for timestamp file}
    B -->|Not found| C[Create timestamp file]
    B -->|Found| D[Find files modified since timestamp]
    C --> D
    D -->|No modified files| E[Display "No files to upload"]
    D -->|Files found| F[Display list of modified files]
    F --> G[Upload modified files]
    G --> H[Update timestamp file]
    H --> I[End: Display success message]
```

## Implementation Details

### 1. Add the `sync` Command

Add a new case to the `run` script for the `sync` command that will:

- Maintain a timestamp file (`.last_sync`) to track when files were last uploaded
- Find all files in the `device/` directory that have been modified since the last upload
- Automatically upload those modified files to the ESP32
- Update the timestamp after successful upload

### 2. Command Options

The sync command will have options:

- `./run sync` - Auto-detect and upload modified files
- `./run sync --dry-run` - Just show which files would be uploaded without actually uploading
- `./run sync --force` - Force upload of all files in device/ directory

### 3. Code Changes

The implementation will require:

1. Adding a new case to the `run` script's command handling
2. Implementing file modification time check functionality
3. Maintaining a timestamp file to track the last sync
4. Leveraging the existing upload functionality to handle the actual file uploads

### 4. Benefits

This approach:

- Doesn't require external dependencies (like git)
- Is fast and efficient (only uploads changed files)
- Works with your existing upload mechanism
- Requires minimal changes to your workflow

## Example Usage

```bash
# Automatically upload all modified files
./run sync

# Just show which files would be uploaded
./run sync --dry-run

# Force upload of all files in device/ directory
./run sync --force
```
