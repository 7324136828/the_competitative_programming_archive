/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        jira: {
          blue: '#0052CC',
          'blue-hover': '#0065FF',
          'blue-light': '#DEEBFF',
          dark: '#172B4D',
          gray: '#5E6C84',
          light: '#F4F5F7',
          border: '#DFE1E6',
        }
      }
    },
  },
  plugins: [],
}
