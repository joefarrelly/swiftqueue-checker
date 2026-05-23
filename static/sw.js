self.addEventListener("push", (event) => {
    const data = event.data.json();
    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
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
