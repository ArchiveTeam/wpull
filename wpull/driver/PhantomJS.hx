import haxe.Json;
import js.Browser;

using StringTools;


class PhantomJS {
    var system:Dynamic;
    var webpage:Dynamic;
    var phantom:Dynamic;
    var fs:Dynamic;
    var page:Dynamic;
    var config:Dynamic;
    var eventLogFile:Dynamic;
    var actionLogFile:Dynamic;
    var activityCounter = 0;
    var pageLoaded = false;

    public function new() {
        system = untyped __js__("require")("system");
        webpage = untyped __js__("require")("webpage");
        phantom = untyped __js__("phantom");
        fs = untyped __js__("require")("fs");
    }

    public static function main() {
        var app = new PhantomJS();
        app.run();
    }

    function logStderrLine(message:String) {
        if (system.stderr != null) {
            return system.stderr.writeLine(message);
        } else {
            return system.stdout.writeLine(message);
        }
    }

    /**
     * Do the entire process pipeline.
     */
    public function run() {
        setUpErrorHandler();
        loadConfig();
        createPage();
        listenPageEvents();
        loadUrl();
    }

    /**
     * Set up error handler which logs to stderr
     */
    function setUpErrorHandler() {
        phantom.onError = function (message:String, traceArray:Array<Dynamic>) {
            logStderrLine(message);

            for (traceLine in traceArray) {
                var source:String;
                var functionName:String = "";

                if (traceLine.file != null) {
                    source = traceLine.file;
                } else {
                    source = traceLine.sourceURL;
                }

                if (Reflect.field(traceLine, "function") != null) {
                    functionName = Reflect.field(traceLine, "function");
                }

                logStderrLine('  $source:${traceLine.line} $functionName');
            }
        }
    }

    /**
     * Load the launch configuration.
     */
    function loadConfig() {
        if (system.args.length != 2) {
            throw "Missing launch configuration.";
        }

        var configContent = fs.read(system.args[1]);
        config = Json.parse(configContent);

        openLogFiles();
    }

    /**
     * Open the event and action log files.
     */
    function openLogFiles() {
        var eventLogFilename:String = Reflect.field(config, "event_log_filename");
        var actionLogFilename:String = Reflect.field(config, "action_log_filename");

        if (eventLogFilename != null) {
            eventLogFile = fs.open(eventLogFilename, "w");
        }

        if (actionLogFilename != null) {
            actionLogFile = fs.open(actionLogFilename, "w");
        }
    }

    /**
     * Create the page and set up the page settings.
     */
    function createPage() {
        page = webpage.create();

        page.evaluate("function () { document.body.bgColor = 'white'; }");
        page.viewportSize = {
            width: Reflect.field(config, 'viewport_width'),
            height: Reflect.field(config, 'viewport_height')
        };

        var paperWidth:Int = Reflect.field(config, 'paper_width');
        var paperHeight:Int = Reflect.field(config, 'paper_height');

        page.paperSize = {
            width: '$paperWidth px',
            height: '$paperHeight px',
            border: "0px"
        };

        page.customHeaders = Reflect.field(config, 'custom_headers');

        var settings = Reflect.field(config, 'page_settings');
        for (name in Reflect.fields(settings)) {
            Reflect.setField(page.settings, name, Reflect.field(settings, name));
        }
    }

    /**
     * Set up the page event callbacks.
     */
    function listenPageEvents() {
        page.onAlert = function (message) {
            logEvent("alert", {message: message});
        }

        page.onClosing = function (closingPage) {
            logEvent("closing");
        }

        page.onConfirm = function (message) {
            logEvent("confirm", {message: message});
            return false;
        }

        page.onConsoleMessage = function (message, lineNum, sourceId) {
            logEvent(
                "console_message",
                {
                    message: message,
                    line_num: lineNum,
                    source_id: sourceId,
                }
            );
        }

        page.onError = function (message, trace) {
            logEvent("error", {message: message, trace: trace});
        }

        page.onFilePicker = function (oldFile) {
            logEvent("file_picker", {old_file: oldFile});
            return null;
        }

        page.onInitialized = function () {
            logEvent("initialized");
        }

        page.onLoadFinished = function (status) {
            logEvent("load_finished", {status: status});
            activityCounter += 1;
        }

        page.onLoadStarted = function () {
            logEvent("load_started");
            activityCounter += 1;
        }

        page.onNavigationRequested = function (url, type, willNavigate, main) {
            logEvent("navigation_requested", {
                'url': url,
                'type': type,
                'will_navigate': willNavigate,
                'main': main
            });
        }

        page.onPageCreated = function (newPage) {
            logEvent("page_created", {});
        }

        page.onPrompt = function (message, defaultValue) {
            logEvent("prompt", {
                message: message,
                default_value: defaultValue,
            });
            return null;
        }

        page.onResourceError = function (resourceError) {
            logEvent("resource_error", {
                resource_error: resourceError,
            });
            activityCounter += 1;
        }

        page.onResourceReceived = function (response) {
            logEvent("resource_received", {
                response: response
            });
            activityCounter += 1;
        }

        page.onResourceRequested = function (requestData, networkRequest) {
            logEvent("resource_requested", {
                request_data: requestData,
                network_request: networkRequest
            });
            activityCounter += 1;
        }

        page.onResourceTimeout = function (request) {
            logEvent("resource_timeout", {
                request: request
            });
            activityCounter += 1;
        }

        page.onUrlChanged = function (targetUrl) {
            logEvent("url_changed", {target_url: targetUrl});
        }
    }

    /**
     * Write a page event to the log.
     */
    function logEvent(eventName:String, ?eventData:Dynamic) {
        if (eventLogFile == null) {
            return;
        }

        var line = Json.stringify({
            timestamp: Date.now().getTime() / 1000.0,
            event: eventName,
            value: eventData
        });
        eventLogFile.write(line);
        eventLogFile.write('\n');
    }

    /**
     * Write a page manipulation action to the log.
     */
    function logAction(eventName:String, ?eventData:Dynamic) {
        if (actionLogFile == null) {
            return;
        }

        var line = Json.stringify({
            timestamp: Date.now().getTime() / 1000.0,
            event: eventName,
            value: eventData
        });
        actionLogFile.write(line);
        actionLogFile.write('\n');
    }

    /**
     * Load the URL.
     */
    function loadUrl() {
        var url:String = Reflect.field(config, "url");

        trace('Load URL $url.');
        page.open(url, function () { pageLoaded = true; });
        // For PhantomJS, we need to poll so that the callback isn't in
        // the page scope but in here scope. If we don't do this,
        // errors don't bubble up and weird security access errors occurs.
        pollPageLoad();
    }

    /**
     * Pool for page loaded.
     */
    function pollPageLoad() {
        if (pageLoaded) {
            loadFinishedCallback();
        } else {
            Browser.window.setTimeout(pollPageLoad, 100);
        }
    }

    /**
     * Callback when page has loaded.
     */
    function loadFinishedCallback() {
        trace("Load finished.");

        if (isPageDynamic()) {
            scrollPage();
        } else {
            loadFinishedCallback2();
        }
    }

    /**
     * Callback when page was scrolled.
     */
    function loadFinishedCallback2() {
        if (Reflect.field(config, 'snapshot')) {
            makeSnapshots();
        }

        close();
    }

    /**
     * Return whether the page uses JavaScript.
     */
    function isPageDynamic():Bool {
        var result:Bool = page.evaluate("
            function () {
            return document.getElementsByTagName('script').length ||
                document.querySelector(
                    '[onload],[onunload],[onabortonclick],[ondblclick],' +
                    '[onmousedown],[onmousemove],[onmouseout],[onmouseover],' +
                    '[onmouseup],[onkeydown],[onkeypress],[onkeyup]');
            }
        ");
        return result;
    }

    /**
     * Scroll the page to the bottom and then back to top.
     */
    function scrollPage() {
        var currentY = 0;
        var scrollDelay:Int = cast(Reflect.field(config, 'wait_time') * 1000, Int);
        var numScrolls:Int = Reflect.field(config, 'num_scrolls');
        var smartScroll:Bool = Reflect.field(config, 'smart_scroll');

        // Try to get rid of any stupid "sign up now" overlays.
        var clickX:Int = page.viewportSize.width;
        var clickY:Int = page.viewportSize.height;
        logAction('click', [clickX, clickY]);
        sendClick(clickX, clickY);

        function cleanupScroll() {
            logAction("set_scroll_left", 0);
            logAction("set_scroll_top", 0);

            setPagePosition(0, 0);
            sendKey(page.event.key.Home);

            loadFinishedCallback2();
        }

        function actualScroll() {
            var beforeActivityCount = activityCounter;
            currentY += 768;

            trace('Scroll page $currentY. numScrolls=$numScrolls.');
            logAction("set_scroll_left", 0);
            logAction("set_scroll_top", currentY);

            setPagePosition(0, currentY);
            sendKey(page.event.key.PageDown);

            Browser.window.setTimeout(function () {
                if (smartScroll && beforeActivityCount == activityCounter) {
                    cleanupScroll();
                    return;
                }

                numScrolls -= 1;

                if (numScrolls > 0) {
                    actualScroll();
                } else {
                    cleanupScroll();
                }
            }, scrollDelay);
        };

        actualScroll();
    }

    /**
     * Scroll the page to a position.
     */
    function setPagePosition(x:Int, y:Int) {
        page.scrollPosition = {left: x, top: y};
        page.evaluate('
            function () {
                if (window) {
                    window.scrollTo($x, $y);
                }
            }
        ');
    }

    /**
     * Send a mouse click to the page.
     */
    function sendClick(x:Int, y:Int, button:String = "left") {
        page.sendEvent("mousedown", x, y, button);
        page.sendEvent("mouseup", x, y, button);
        page.sendEvent("click", x, y, button);
    }

    /**
     * Send a keyboard event to the page.
     */
    function sendKey(key:Int, modifier:Int = 0) {
        page.sendEvent("keypress", key, null, null, modifier);
        page.sendEvent("keydown", key, null, null, modifier);
        page.sendEvent("keyup", key, null, null, modifier);
    }

    /*
     * Render the snapshot files.
     */
    function makeSnapshots() {
        var paths:Array<String> = Reflect.field(config, "snapshot_paths");

        for (path in paths) {
            trace('Making snapshot $path');
            renderPage(path);
        }
    }

    /*
     * Render page and save to given path.
     */
    function renderPage(path:String) {
        if (path.endsWith(".html")) {
            var file = fs.open(path, "w");
            file.write(page.content);
            file.close();
        } else {
            page.render(path);
        }
    }

    /*
     * Clean up and exit.
     */
    function close() {
        trace("Closing.");
        page.close();

        if (actionLogFile != null) {
            actionLogFile.flush();
            // XXX: Segfault on at least 1.9.8
            // actionLogFile.close();
        }

        if (eventLogFile != null) {
            eventLogFile.flush();
            // XXX: Segfault on at least 1.9.8
            // eventLogFile.close();
        }

        phantom.exit();
    }
}
