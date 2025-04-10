#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

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

function processFiles(jsonData) {
  function generateTree(entries, prefix) {
    let res = [];
    for (let i = 0; i < entries.length; i++) {
      let entry = entries[i];

      // Skip files matching the pattern *###.* (contains 3 digits followed by a dot)
      if (!entry.is_dir && /\d{3}\./.test(entry.name)) {
        continue;
      }

      let isLast = i === entries.length - 1;
      let branch = isLast ? "└── " : "├── ";
      if (entry.is_dir === true) {
        let line = `${prefix}${branch}${entry.name}/ <DIR>`;
        res.push({ path: entry.path, display: line, selected: false });
        if (entry.children && Array.isArray(entry.children)) {
          let newPrefix = prefix + (isLast ? "    " : "│   ");
          res.push(...generateTree(entry.children, newPrefix));
        }
      } else {
        let line = `${prefix}${branch}${entry.name} (${
          entry.size_formatted || "0B"
        })`;
        res.push({ path: entry.path, display: line, selected: false });
      }
    }
    return res;
  }
  if (!Array.isArray(jsonData)) {
    console.log("Error: Expected JSON array but got:", typeof jsonData);
    return [];
  }
  return generateTree(jsonData, "");
}

function formatForDialog(fileEntries) {
  return fileEntries
    .map((entry) => `"${entry.path}" "${entry.display}" off`)
    .join("\n");
}

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
