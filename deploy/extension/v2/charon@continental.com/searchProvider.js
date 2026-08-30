// searchProvider.js
import Gio from 'gi://Gio';
import St from 'gi://St';

export class CharonSearchProvider {
    constructor(extensionInstance) {
        this.id = 'charon-search-provider';
        this.extension = extensionInstance;

        // Use native Gio.AppInfo so GNOME Shell can query .should_show() cleanly
        this.appInfo = Gio.AppInfo.create_from_commandline(
            'charon-cli',
            'Charon Assistant',
            Gio.AppInfoCreateFlags.NONE
        );
    }

    async getInitialResultSet(terms, cancellable) {
        return new Promise((resolve) => {
            if (cancellable && cancellable.is_cancelled()) {
                return resolve([]);
            }

            const query = terms.join(' ');
            if (query.startsWith('c:') || query.startsWith('charon:')) {
                resolve(['charon-task']);
            } else {
                resolve([]);
            }
        });
    }

    async getSubsearchResultSet(previousResults, terms, cancellable) {
        // Delegate to the initial result logic to keep it DRY
        return this.getInitialResultSet(terms, cancellable);
    }

    async getResultMetas(resultIds, cancellable) {
        return new Promise((resolve) => {
            if (cancellable && cancellable.is_cancelled()) {
                return resolve([]);
            }

            const metas = resultIds.map(id => ({
                id: id,
                name: 'Ask Charon',
                description: 'Send this command to the Charon daemon.',
                createIcon: (size) => new St.Icon({
                    icon_name: 'system-run-symbolic',
                    icon_size: size
                })
            }));

            resolve(metas);
        });
    }

    filterResults(results, maxResults) {
        return results.slice(0, maxResults);
    }

    activateResult(resultId, terms) {
        let query = terms.join(' ').replace(/^c:\s*|^charon:\s*/, '');

        // Strip out the prefix and send the pure task to the daemon
        if (this.extension && typeof this.extension.submitTask === 'function') {
            this.extension.submitTask(query);
        }
    }
}