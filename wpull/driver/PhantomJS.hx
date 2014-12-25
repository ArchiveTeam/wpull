using StringTools;

class PhantomJS {
    var system : Dynamic;
    var webpage : Dynamic;
    var phantom : Dynamic;
    var fs : Dynamic;
    var page : Dynamic;
    var pollTimer : Dynamic;

    public function new() {
        system = untyped __js__("require")("system");
        webpage = untyped __js__("require")("webpage");
        phantom = untyped __js__("phantom");
        fs = untyped __js__("require")("fs");

        pollTimer = untyped __js__("setInterval")(pollForCommand, 100);
    }

    public static function main() {
        var app = new PhantomJS();
    }

    private function pollForCommand() {
        sendMessage({event: "poll"});
        var commandMessage = readMessage();
        var replyValue = null;

        switch commandMessage.command {
            case "new_page":
                newPage();
            case "open_url":
                page.open(commandMessage.url);
                listenEvents();
            case "close_page":
                page.close();
                page = null;
            case "set_page_size":
                setPageSize(
                    commandMessage.viewport_width,
                    commandMessage.viewport_height,
                    commandMessage.paper_width,
                    commandMessage.paper_height
                );
            case "render_page":
                renderPage(commandMessage.path);
            case "set_page_custom_headers":
                setPageCustomHeaders(commandMessage.headers);
            case "set_page_settings":
                setPageSettings(commandMessage.settings);
            case "scroll_page":
                scrollPage(commandMessage.x, commandMessage.y);
            case "exit":
                exit(commandMessage.exit_code);
            case "get_page_url":
                replyValue = page.url;
            case "click":
                sendClick(commandMessage.x, commandMessage.y, commandMessage.button);
            case "key":
                sendKey(commandMessage.key, commandMessage.modifier);
            case "is_page_dynamic":
                replyValue = isPageDynamic();
            case null:
                return;
            default:
                trace("Unknown command");
        }

        sendMessage({
            event: "reply", value: replyValue,
            reply_id: commandMessage.message_id
        });
    }

    private function sendMessage(message : Dynamic) {
        var messageString = untyped __js__("JSON").stringify(message);
        system.stdout.write("!RPC ");
        system.stdout.writeLine(messageString);
    }

    private function readMessage() : Dynamic {
        var messageString = system.stdin.readLine();
        var message = untyped __js__("JSON").parse(messageString.slice(5));
        return message;
    }

    private function sendEvent(eventName: String, ? args : Dynamic) : Dynamic {
        if (!args) {
            args = {};
        }

        var message = args;
        args.event = eventName;

        sendMessage(message);

        var reply = readMessage();

        return reply.value;
    }

    private function newPage() {
        if (page) {
            closePage();
        }

        page = webpage.create();
        page.evaluate("function () { document.body.bgColor = 'white'; }");
    }

    private function closePage() {
        page.close();
        page = null;
    }

    private function renderPage(path : String) {
        if (path.endsWith(".html")) {
            var file = fs.open(path, "w");
            file.write(page.content);
            file.close();
        } else {
            page.render(path);
        }
    }

    private function setPageSize(viewportWidth : Int, viewportHeight : Int,
                                 paperWidth : Int, paperHeight: Int) {
        page.viewportSize = {
            width: viewportWidth,
            height: viewportHeight
        };
        page.paperSize = {
            width: '$paperWidth px',
            height: '$paperHeight px',
            border: "0px"
        };
    }

    private function setPageSettings(settings : Dynamic) {
        for (name in Reflect.fields(settings)) {
            Reflect.setField(page.settings, name, Reflect.field(settings, name));
        }
    }

    private function setPageCustomHeaders(headers : Dynamic) {
        page.customHeaders = headers;
    }

    private function scrollPage(x : Int, y : Int) {
        page.scrollPosition = {left: x, top: y};
        page.evaluate('
            function () {
                if (window) {
                    window.scrollTo($x, $y);
                }
            }
        ');
    }

    private function sendClick(x : Int, y : Int, button : String) {
        page.sendEvent("mousedown", x, y, button);
        page.sendEvent("mouseup", x, y, button);
        page.sendEvent("click", x, y, button);
    }

    private function sendKey(key : Int, modifier : Int) {
        page.sendEvent("keypress", key, null, null, modifier);
        page.sendEvent("keydown", key, null, null, modifier);
        page.sendEvent("keyup", key, null, null, modifier);
    }

    private function isPageDynamic() : Bool {
        var result : Bool = page.evaluate("
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

    private function listenEvents() {
        page.onAlert = function (message) {
            sendEvent("alert", {message: message});
        }

        page.onClosing = function (closingPage) {
            sendEvent("closing");
        }

        page.onConfirm = function (message) {
            return sendEvent("confirm", {message: message});
        }

        page.onConsoleMessage = function (message, lineNum, sourceId) {
            sendEvent(
                "console_message",
                {
                    message: message,
                    line_num: lineNum,
                    source_id: sourceId,
                }
            );
        }

        page.onError = function (message, trace) {
            sendEvent("error", {message: message, trace: trace});
        }

        page.onFilePicker = function (oldFile) {
            return sendEvent("file_picker", {old_file: oldFile});
        }

        page.onInitialized = function () {
            sendEvent("initialized");
        }

        page.onLoadFinished = function (status) {
            sendEvent("load_finished", {status: status});
        }

        page.onLoadStarted = function () {
            sendEvent("load_started");
        }

        page.onNavigationRequested = function (url, type, willNavigate, main) {
            sendEvent("navigation_requested", {
                'url': url,
                'type': type,
                'will_navigate': willNavigate,
                'main': main
            });
        }

        page.onPageCreated = function (newPage) {
            sendEvent("page_created", {});
        }

        page.onPrompt = function (message, defaultValue) {
            return sendEvent("prompt", {
                message: message,
                default_value: defaultValue,
            });
        }

        page.onResourceError = function (resourceError) {
            sendEvent("resource_error", {
                resource_error: resourceError,
            });
        }

        page.onResourceReceived = function (response) {
            sendEvent("resource_received", {
                response: response
            });
        }

        page.onResourceRequested = function (requestData, networkRequest) {
            var reply = sendEvent("resource_requested", {
                request_data: requestData,
                network_request: networkRequest
            });

            if (!reply) {
                return;
            }

            if (cast(reply, String) == 'abort') {
                networkRequest.abort();
            } else if (reply) {
                networkRequest.changeUrl(reply);
            }
        }

        page.onResourceTimeout = function (request) {
            sendEvent("resource_timeout", {
                request: request
            });
        }

        page.onUrlChanged = function (targetUrl) {
            sendEvent("url_changed", {target_url: targetUrl});
        }
    }

    private function exit(exitCode : Int = 0) {
        if (pollTimer) {
            untyped __js__("clearTimeout")(pollTimer);
            pollTimer = null;
        }
        phantom.exit(exitCode);
    }
}
