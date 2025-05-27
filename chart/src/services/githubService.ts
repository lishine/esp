// chart/src/services/githubService.ts

// Define the structure for a file item from the GitHub API (simplified)
interface GitHubFile {
	name: string
	path: string
	sha: string
	size: number
	url: string
	html_url: string
	git_url: string
	download_url: string | null // download_url can be null for directories
	type: 'file' | 'dir'
	// _links: { self: string; git: string; html: string } // Not strictly needed for this service
}

// Define the structure for the list of files we want to work with
export interface LogFileListItem {
	name: string
	downloadUrl: string
}

const GITHUB_API_BASE_URL = 'https://api.github.com'
const REPO_OWNER = 'lishine'
const REPO_NAME = 'esp'
const LOGS_PATH = 'data_logs'

/**
 * Fetches the list of .jsonl log files from the specified GitHub repository and path.
 * Filters for .jsonl files and ensures they have a download_url.
 * @returns A promise that resolves to an array of LogFileListItem.
 */
export async function fetchGitHubLogFilesList(): Promise<LogFileListItem[]> {
	const apiUrl = `${GITHUB_API_BASE_URL}/repos/${REPO_OWNER}/${REPO_NAME}/contents/${LOGS_PATH}`

	try {
		const response = await fetch(apiUrl, {
			method: 'GET',
			headers: {
				// No 'Authorization' header needed for public repos,
				// but 'Accept' is good practice.
				Accept: 'application/vnd.github.v3+json',
			},
		})

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}))
			throw new Error(
				`GitHub API Error: ${response.status} ${response.statusText}. ${errorData.message || ''}`.trim()
			)
		}

		const files = (await response.json()) as GitHubFile[]

		if (!Array.isArray(files)) {
			console.error('GitHub API did not return an array for path:', LOGS_PATH, files)
			throw new Error('Unexpected response format from GitHub API when listing files.')
		}

		const logFiles: LogFileListItem[] = files
			.filter((file) => file.type === 'file' && file.name.endsWith('.jsonl') && file.download_url)
			.map((file) => ({
				name: file.name,
				downloadUrl: file.download_url!, // Assert non-null as we filtered for it
			}))

		return logFiles
	} catch (error) {
		console.error('Failed to fetch GitHub log files list:', error)
		throw error // Re-throw to be caught by the caller in the store
	}
}

/**
 * Fetches the raw content of a specific file from GitHub using its download URL.
 * @param downloadUrl The direct download URL for the file.
 * @returns A promise that resolves to the raw text content of the file.
 */
export async function fetchGitHubFileContent(downloadUrl: string): Promise<string> {
	try {
		const response = await fetch(downloadUrl, {
			method: 'GET',
			// No specific headers usually needed for direct download_url
		})

		if (!response.ok) {
			// For download_url, response might not be JSON, so just use statusText
			throw new Error(`Failed to download file: ${response.status} ${response.statusText}`)
		}

		const rawContent = await response.text()
		return rawContent
	} catch (error) {
		console.error(`Failed to fetch GitHub file content from ${downloadUrl}:`, error)
		throw error // Re-throw to be caught by the caller in the store
	}
}
