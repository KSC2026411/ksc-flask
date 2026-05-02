// static/js/admin_announcements.js

// Initialize Quill editor
var quill = new Quill('#editor', {
    theme: 'snow',
    placeholder: 'Write your announcement...',
    modules: {
        toolbar: [
            ['bold', 'italic', 'underline'],
            [{ 'list': 'ordered'}, { 'list': 'bullet' }],
            ['link'],
            ['clean']
        ]
    }
});

// Connect to Socket.IO
const socket = io("/customer");

// Handle form submission
document.querySelector('#announcement-form').onsubmit = function(e) {
    // Put editor content into hidden input for DB save
    document.querySelector('#hidden-message').value = quill.root.innerHTML;

    // Prepare data for real-time broadcast
    const data = {
        title: this.title.value,
        message: quill.root.innerHTML,
        created_at: new Date().toISOString()
    };

    // Emit live announcement to all connected customers
    socket.emit("cargo_update", data);

    return true; // allow normal form POST to continue saving in DB
};