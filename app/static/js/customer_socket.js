// app/static/js/customer_socket.js

// Connect to the customer namespace
const socket = io("/customer");

// Confirm connection
socket.on("connect", () => {
    console.log("Connected to live cargo updates.");
});

// Listen for cargo updates (from admin or background updater)
socket.on("cargo_update", (data) => {
    console.log("Live update received:", data);

    // Example: update a table or list in the dashboard
    const list = document.getElementById("announcements-list"); // Replace with your element ID
    if (list) {
        const li = document.createElement("li");
        li.className = "list-group-item";
        li.innerHTML = `
            <div class="mb-1">
                <strong>${data.title || "Cargo #" + data.cargo_id}</strong>
                <span class="text-muted small">
                    ${data.last_updated || ""}
                </span>
            </div>
            <div>${data.message || data.status}</div>
        `;
        list.prepend(li); // newest at the top
    }
});

// Optional: handle disconnect
socket.on("disconnect", () => {
    console.log("Disconnected from live updates.");
});