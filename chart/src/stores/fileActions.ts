import { ofetch, FetchError } from 'ofetch'
import { fetchGitHubLogFilesList, fetchGitHubFileContent, type LogFileListItem } from '../services/githubService'
import type { SessionState } from './types'

export interface FileActionContext
	extends Pick<
		SessionState,
		| 'sessionMetadata'
		| 'logEntries'
		| 'isLoading'
		| 'error'
		| 'userApiIp'
		| 'useUserApiIp'
		| 'gitHubFiles'
		| 'isGitHubListLoading'
		| 'gitHubListError'
		| 'isGitHubFileLoading'
		| 'gitHubFileError'
		| 'currentFileSource'
		| 'currentGitHubFileName'
	> {
	_parseSessionData: (fullDataString: string) => void
}

export const fileActions = {
	async handleFileUpload(this: FileActionContext, file: File) {
		this.isLoading = true
		this.error = null
		this.sessionMetadata = null
		this.logEntries = []
		this.currentFileSource = 'local'
		this.currentGitHubFileName = null

		try {
			const text = await file.text()
			this._parseSessionData(text)
		} catch (err) {
			console.error('Error processing uploaded file:', err)
			this.error = err instanceof Error ? err.message : 'An unknown error occurred while processing the file'
		} finally {
			this.isLoading = false
		}
	},

	async fetchSessionData(this: FileActionContext, prevOffset?: number) {
		this.isLoading = true
		this.error = null
		this.sessionMetadata = null
		this.logEntries = []

		try {
			const protocol = 'https'
			let effectiveIp = '192.168.4.1'

			if (this.useUserApiIp && this.userApiIp) {
				if (this.userApiIp.match(/^(\d{1,3}\.){3}\d{1,3}$/) || this.userApiIp.includes(':')) {
					effectiveIp = this.userApiIp
				} else {
					console.warn('Invalid custom IP format, using default:', this.userApiIp)
				}
			}

			const apiUrl = `${protocol}://${effectiveIp}/api/data`
			console.log(
				`Fetching data from: ${apiUrl} (DEV: ${String(import.meta.env.DEV)}, useUserApiIp: ${String(this.useUserApiIp)}, userApiIp: ${this.userApiIp}, prevOffset: ${prevOffset})`
			)

			const fetchOptions: RequestInit = {
				method: 'POST',
			}

			if (prevOffset && prevOffset > 0) {
				fetchOptions.body = JSON.stringify({ prev: prevOffset })
				fetchOptions.headers = { 'Content-Type': 'application/json' }
			}

			const response = await ofetch(apiUrl, {
				...fetchOptions,
				parseResponse: (txt) => txt,
				retry: 3,
				retryDelay: 500,
				timeout: 10,
				onRequestError: ({ error }) => {
					console.error('Request error:', error)
					throw error
				},
				onResponseError: ({ response }) => {
					console.error('Response error:', response.status, response._data)
					throw new Error(`API error: ${response.status.toString()}`)
				},
			})
			this._parseSessionData(response)
		} catch (err) {
			console.error('Error fetching or parsing session data:', err)
			if (err instanceof FetchError) {
				this.error = `Network error: ${err.message}`
			} else {
				this.error = err instanceof Error ? err.message : 'An unknown error occurred'
			}
		} finally {
			this.isLoading = false
		}
	},

	async fetchAndSetGitHubLogFilesList(this: FileActionContext) {
		this.isGitHubListLoading = true
		this.gitHubListError = null
		try {
			this.gitHubFiles = await fetchGitHubLogFilesList()
		} catch (err) {
			console.error('Error fetching GitHub log files list in store:', err)
			this.gitHubListError = err instanceof Error ? err.message : 'Failed to fetch GitHub file list.'
			this.gitHubFiles = []
		} finally {
			this.isGitHubListLoading = false
		}
	},

	async loadLogFileFromGitHub(this: FileActionContext, file: LogFileListItem) {
		this.isGitHubFileLoading = true
		this.gitHubFileError = null
		this.sessionMetadata = null
		this.logEntries = []
		this.error = null

		try {
			const rawContentString = await fetchGitHubFileContent(file.downloadUrl)
			this._parseSessionData(rawContentString)
			this.currentFileSource = 'github'
			this.currentGitHubFileName = `/github/${file.name}`
		} catch (err) {
			console.error(`Error loading log file ${file.name} from GitHub in store:`, err)
			this.gitHubFileError = err instanceof Error ? err.message : `Failed to load ${file.name} from GitHub.`
			this.sessionMetadata = null
			this.logEntries = []
			this.currentFileSource = null
			this.currentGitHubFileName = null
		} finally {
			this.isGitHubFileLoading = false
		}
	},

	clearGitHubData(this: FileActionContext) {
		this.sessionMetadata = null
		this.logEntries = []
		this.currentFileSource = null
		this.currentGitHubFileName = null
		this.gitHubFileError = null
		console.log('Cleared GitHub specific file data.')
	},
}
