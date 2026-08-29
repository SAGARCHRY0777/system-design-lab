import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import hooks from 'eslint-plugin-react-hooks'

export default [
  { ignores: ['dist/**'] },
  js.configs.recommended,
  // scripts/ runs under Node, not in the browser -- console, process and URL
  // are legitimate there and undefined in the app.
  {
    files: ['scripts/**/*.mjs'],
    languageOptions: { ecmaVersion: 2022, globals: globals.node, sourceType: 'module' },
  },
  {
    files: ['src/**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true }, sourceType: 'module' },
    },
    settings: { react: { version: '18.2' } },
    plugins: { react, 'react-hooks': hooks },
    rules: {
      ...react.configs.recommended.rules,
      ...hooks.configs.recommended.rules,
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
    },
  },
]
