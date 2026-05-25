self.addEventListener("push", (event) => {
    let data = {};
    try {
        data = event.data?.json() ?? {};
    } catch {
        data = { title: "SwiftQueue", body: event.data?.text() ?? "" };
    }
    event.waitUntil(
        self.registration.showNotification(data.title ?? "SwiftQueue", {
            body: data.body ?? "",
            data: { url: data.url },
        })
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const url = event.notification.data?.url;
    if (url) {
        event.waitUntil(clients.openWindow(url));
    }
});
