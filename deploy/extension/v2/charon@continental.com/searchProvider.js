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

    getInitialResultSet(terms, callback, cancellable) {
        let query = terms.join(' ');
        if (query.startsWith('c:') || query.startsWith('charon:')) {
            callback(['charon-task']);
        } else {
            callback([]);
        }
    }

    getSubsearchResultSet(previousResults, terms, callback, cancellable) {
        // Evaluate terms directly without calling getInitialResultSet to prevent recursion
        let query = terms.join(' ');
        if (query.startsWith('c:') || query.startsWith('charon:')) {
            callback(['charon-task']);
        } else {
            callback([]);
        }
    }

    getResultMetas(resultIds, callback, cancellable) {
        let metas = resultIds.map(id => ({
            id: id,
            name: 'Ask Charon',
            description: 'Send this command to the Charon daemon.',
            createIcon: (size) => new St.Icon({
                icon_name: 'system-run-symbolic',
                icon_size: size
            })
        }));
        callback(metas);
    }

    filterResults(results, maxResults) {
        return results.slice(0, maxResults);
    }

    activateResult(resultId, terms) {
        let query = terms.join(' ').replace(/^c:\s*|^charon:\s*/, '');
        // Fixed: Called public method submitTask instead of non-existent _submitTask
        if (this.extension && typeof this.extension.submitTask === 'function') {
            this.extension.submitTask(query);
        }
    }
}