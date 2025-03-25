#!/usr/bin/env node

/**
 * ESP32 File System JSON Parser
 * Extracts and processes JSON data from ESP32 file listings
 */

const fs = require("fs");
const path = require("path");

/**
 * Extract valid JSON from potentially mixed output
 * @param {string} rawData - Raw output from ESP32 file listing command
 * @returns {object} Parsed JSON object or null if extraction failed
 */
function extractJson(rawData) {
  // First attempt: Try to parse the entire output as JSON
  try {
    return JSON.parse(rawData);
  } catch (e) {
    console.log(
      "Could not parse entire output as JSON. Trying to extract JSON array..."
    );

    // Second attempt: Try to find a JSON array in the output
    const jsonArrayMatch = rawData.match(/^\[([\s\S]*)\]$/m);
    if (jsonArrayMatch) {
      try {
        console.log("Found JSON array starting at beginning of a line");
        return JSON.parse(`[${jsonArrayMatch[1]}]`);
      } catch (e) {
        console.log("Error: Could not parse extracted array content as JSON.");
      }
    }

    // Third attempt: Try to extract any JSON object or array using regex
    const jsonMatch = rawData.match(/\[([\s\S]*?)\]/);
    if (jsonMatch) {
      try {
        console.log("Found JSON-like pattern in the output");
        return JSON.parse(`[${jsonMatch[1]}]`);
      } catch (e) {
        console.log("Error: Could not parse extracted content as JSON.");
      }
    }
  }

  console.log("Error: Could not find valid JSON in the output.");
  return null;
}

/**
 * Process file list recursively to create a hierarchical display
 * @param {object} jsonData - Parsed JSON data of files and directories
 * @param {string} prefix - Current path prefix for display
 * @param {number} depth - Current recursion depth
 * @returns {Array} Array of formatted file entries for dialog display
 */
function processFiles(jsonData, prefix = "", depth = 0) {
  const result = [];

  // Safety check to prevent infinite recursion
  if (depth > 10) {
    console.log(
      "Warning: Maximum directory depth reached (10). Stopping recursion."
    );
    return result;
  }

  if (!Array.isArray(jsonData)) {
    console.log("Error: Expected JSON array but got:", typeof jsonData);
    return result;
  }

  console.log(`Found ${jsonData.length} items in the JSON array`);

  // Iterate over each item in the JSON array
  for (let i = 0; i < jsonData.length; i++) {
    const item = jsonData[i];

    // Extract fields from the current item
    const name = item.name || "";
    const filePath = item.path || "";
    const isDir = item.is_dir === true;
    const size = item.size_formatted || "0B";

    // Skip if name or path is empty
    if (!name || !filePath) {
      console.log(`Warning: Item ${i} has empty name or path, skipping`);
      continue;
    }

    // Process directories
    if (isDir) {
      // Add the directory name with a trailing slash
      const newPrefix = `${prefix}${name}/`;
      console.log(`Processing directory: ${newPrefix}`);

      // Check if the directory has children
      if (item.children && Array.isArray(item.children)) {
        // Recursively process the children
        const childResults = processFiles(item.children, newPrefix, depth + 1);
        result.push(...childResults);
      }
    } else {
      // Process files
      const display = `${prefix}${name}`;
      result.push({
        path: filePath,
        display: `${display} (${size})`,
        selected: false,
      });
    }
  }

  return result;
}

/**
 * Format file entries for dialog display
 * @param {Array} fileEntries - Array of file entry objects
 * @returns {string} Formatted string for dialog display
 */
function formatForDialog(fileEntries) {
  return fileEntries
    .map((entry) => `"${entry.path}" "${entry.display}" off`)
    .join("\n");
}

/**
 * Main function to parse ESP32 file listing
 * @param {string} inputFile - Path to file containing raw ESP32 output
 * @param {string} outputFile - Path to write formatted dialog entries
 * @returns {boolean} Success status
 */
function parseEsp32FileList(inputFile, outputFile) {
  try {
    // Read the raw file data
    const rawData = fs.readFileSync(inputFile, "utf8");

    // Extract JSON from the raw data
    const jsonData = extractJson(rawData);
    if (!jsonData) {
      console.log("Failed to extract valid JSON data");
      return false;
    }

    // Process the file list
    const fileEntries = processFiles(jsonData);
    if (fileEntries.length === 0) {
      console.log("No files found or could not parse the file list");
      return false;
    }

    // Format for dialog and write to output file
    const dialogContent = formatForDialog(fileEntries);
    fs.writeFileSync(outputFile, dialogContent);

    console.log(`Successfully processed ${fileEntries.length} file entries`);
    return true;
  } catch (error) {
    console.error("Error processing ESP32 file list:", error.message);
    return false;
  }
}

// If this script is run directly (not imported)
if (require.main === module) {
  if (process.argv.length < 4) {
    console.log("Usage: node rm-visual-parsing.js <input-file> <output-file>");
    process.exit(1);
  }

  const inputFile = process.argv[2];
  const outputFile = process.argv[3];

  const success = parseEsp32FileList(inputFile, outputFile);
  process.exit(success ? 0 : 1);
}

// Export functions for use in other scripts
module.exports = {
  extractJson,
  processFiles,
  formatForDialog,
  parseEsp32FileList,
};
