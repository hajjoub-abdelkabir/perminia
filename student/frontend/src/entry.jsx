if (import.meta.env.VITE_APP_MODE === 'static-demo') {
  import('./demo/DemoApp.jsx');
} else {
  import('./main.jsx');
}
