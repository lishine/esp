const fs = require("fs");
const readline = require("readline");

// Function to calculate distance between two points using Haversine formula
function haversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371e3; // metres
  const φ1 = (lat1 * Math.PI) / 180; // φ, λ in radians
  const φ2 = (lat2 * Math.PI) / 180;
  const Δφ = ((lat2 - lat1) * Math.PI) / 180;
  const Δλ = ((lon2 - lon1) * Math.PI) / 180;

  const a =
    Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
    Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  const d = R * c; // in metres
  return d;
}

async function extractGpsData(filePath) {
  const fileStream = fs.createReadStream(filePath);

  const rl = readline.createInterface({
    input: fileStream,
    crlfDelay: Infinity,
  });

  const gpsTrack = [];

  for await (const line of rl) {
    try {
      const data = JSON.parse(line);
      if (Array.isArray(data)) {
        // Check if data is an array
        for (const entry of data) {
          if (entry.n === "gps" && entry.v && entry.v.fix === true) {
            gpsTrack.push({
              lat: entry.v.lat,
              lon: entry.v.lon,
            });
          }
        }
      }
    } catch (error) {
      console.error(`Error parsing line: ${line}`, error);
    }
  }

  return gpsTrack;
}

// Example usage:
// Replace 'path/to/your/log.jsonl' with the actual path to your data file.
const logFilePath = process.argv[2];

if (!logFilePath) {
  console.error("Usage: node extract_gps_data.js <path_to_log_file.jsonl>");
  process.exit(1);
}

extractGpsData(logFilePath)
  .then((gpsData) => {
    let totalDistance = 0;
    for (let i = 0; i < gpsData.length - 1; i++) {
      totalDistance += haversineDistance(
        gpsData[i].lat,
        gpsData[i].lon,
        gpsData[i + 1].lat,
        gpsData[i + 1].lon
      );
    }

    // Output total distance to distance.txt
    fs.writeFile(
      "distance.txt",
      `Total Distance: ${totalDistance.toFixed(2)} meters`,
      (err) => {
        if (err) {
          console.error("Error writing distance file:", err);
        } else {
          console.log("Total distance written to distance.txt");
        }
      }
    );

    // Output GPS track to console (for plain text table)
    gpsData.forEach((point) => {
      console.log(`${point.lat},${point.lon}`);
    });
  })
  .catch((err) => {
    console.error("Error extracting GPS data:", err);
  });
