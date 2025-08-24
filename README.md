# Routes MCP - Real-time Transit for Israel

An MCP (Model Context Protocol) server that provides real-time public transit information for Israel, combining Google Routes API, Google Places API, and GTFS data with curlbus for accurate arrival times.

## Features

- Get transit routes between any two addresses in Israel
- Hebrew-localized times and addresses
- Real-time bus/train arrival information via curlbus
- Automatic city detection using Google Places API
- GTFS-based stop code matching for accurate real-time data
- Configurable number of routes returned

## Google API Setup

### 1. Create a Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one

### 2. Enable Required APIs
Enable these APIs in your Google Cloud project:

1. **Routes API**
   - Go to [Routes API](https://console.cloud.google.com/apis/library/routes.googleapis.com)
   - Click "Enable"

2. **Places API (New)**
   - Go to [Places API (New)](https://console.cloud.google.com/apis/library/places-backend.googleapis.com)
   - Click "Enable"

### 3. Create API Key
1. Go to [API Keys](https://console.cloud.google.com/apis/credentials)
2. Click "Create Credentials" → "API Key"
3. Copy your API key
4. (Optional) Restrict the key to only Routes API and Places API for security

## Installation

### Prerequisites
- Install [uv](https://docs.astral.sh/uv/) package manager
- Python 3.8+

### Setup
```bash
git clone <your-repo-url>
cd routes_mcp
```

## Configuration

### Claude Desktop
Add to your Claude Desktop configuration file (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "routes-israel": {
      "command": "uv",
      "args": ["run", "server.py"],
      "cwd": "/path/to/routes_mcp",
      "env": {
        "GOOGLE_API_KEY": "your_google_api_key_here",
        "MAX_ROUTES": "2"
      }
    }
  }
}
```

### Other MCP Clients (Cursor, etc.)
Same configuration as Claude Desktop - all MCP clients use the same protocol.

### Manual Python Installation
If you prefer traditional pip:
```bash
pip install fastmcp httpx pydantic
```

Then use:
```json
{
  "mcpServers": {
    "routes-israel": {
      "command": "python",
      "args": ["/path/to/routes_mcp/server.py"],
      "env": {
        "GOOGLE_API_KEY": "your_google_api_key_here",
        "MAX_ROUTES": "2"
      }
    }
  }
}
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | ✅ Yes | - | Your Google API key with Routes and Places API enabled |
| `MAX_ROUTES` | No | `2` | Maximum number of routes to return (for performance) |

## Usage

The server provides one tool: `get_route`

### Example
```
Get transit routes from "תל אביב" to "ירושלים"
```

### Response Format
```json
{
  "routes": [
    [
      {
        "operator": "אגד",
        "route_number": "405",
        "departure_stop": "תחנה מרכזית תל אביב/קומה 3/רציף 16",
        "arrival_stop": "תחנה מרכזית ירושלים/יעקב פת/רציף 15",
        "departure_time": "17:16",
        "arrival_time": "17:47",
        "real_time_data": {
          "arrivals": ["13 min", "28 min"],
          "next_arrival": "13 min",
          "status": "success"
        }
      }
    ]
  ]
}
```

## How It Works

1. **Google Routes API**: Gets transit directions with Hebrew localization
2. **Google Places API**: Extracts origin city from place_id for accurate GTFS matching
3. **GTFS API**: Finds exact stop codes based on city and station names
4. **Curlbus Integration**: Gets real-time arrival data using GTFS stop codes
5. **Optimization**: Only fetches real-time data for the first step of each route

## Development

### Running the Server
```bash
GOOGLE_API_KEY="your_key" uv run server.py
```

### Testing Individual Components
```bash
# Test Google Routes API
curl -X POST -H 'Content-Type: application/json' \
  -H 'X-Goog-Api-Key: your_key' \
  -H 'X-Goog-FieldMask: routes.legs.steps.transitDetails,routes.geocodingResults' \
  -d '{"languageCode":"he-IL","origin":{"address":"address1"},"destination":{"address":"address2"},"travelMode":"TRANSIT"}' \
  'https://routes.googleapis.com/directions/v2:computeRoutes'

# Test Google Places API
curl -X GET -H 'X-Goog-Api-Key: your_key' \
  -H 'X-Goog-FieldMask: addressComponents' \
  'https://places.googleapis.com/v1/places/PLACE_ID?languageCode=he'
```

### Logs
Monitor logs for debugging:
```bash
tail -f /tmp/routes_mcp.log
```

## Architecture

- **Google Routes API**: Provides transit routing with Hebrew localization
- **Google Places API**: Converts place_id to city names for GTFS matching  
- **GTFS API**: Israeli public transit stop database for accurate matching
- **Curlbus**: Real-time arrival data from Israeli transit operators
- **Optimization**: Limits to first 2 routes, real-time data only for first transit step

## API Rate Limits & Performance

- Routes limited to `MAX_ROUTES` (default: 2) for faster responses
- Real-time data only fetched for first transit step per route
- Timeouts: 8s for GTFS lookup, 3s for real-time data
- All external API calls are properly timed out to prevent hanging