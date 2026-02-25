# Getting Started with Create React App

This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).

## Available Scripts

In the project directory, you can run:

### `npm start`

Runs the app in the development mode.\
Open [http://localhost:3000](http://localhost:3000) to view it in your browser.

The page will reload when you make changes.\
You may also see any lint errors in the console.

### `npm test`

Launches the test runner in the interactive watch mode.\
See the section about [running tests](https://facebook.github.io/create-react-app/docs/running-tests) for more information.

### `npm run build`

Builds the app for production to the `build` folder.\
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.\
Your app is ready to be deployed!

See the section about [deployment](https://facebook.github.io/create-react-app/docs/deployment) for more information.

### `npm run eject`

**Note: this is a one-way operation. Once you `eject`, you can't go back!**

If you aren't satisfied with the build tool and configuration choices, you can `eject` at any time. This command will remove the single build dependency from your project.

Instead, it will copy all the configuration files and the transitive dependencies (webpack, Babel, ESLint, etc) right into your project so you have full control over them. All of the commands except `eject` will still work, but they will point to the copied scripts so you can tweak them. At this point you're on your own.

You don't have to ever use `eject`. The curated feature set is suitable for small and middle deployments, and you shouldn't feel obligated to use this feature. However we understand that this tool wouldn't be useful if you couldn't customize it when you are ready for it.

## Seat Statuses

Both the client and the admin interface rely on the `/seat` API to obtain the
current status of every seat in a tour.

- **Client mode** &mdash; the API returns only two statuses:
  - `available` &mdash; the seat can be selected and is highlighted in green;
  - `blocked` &mdash; the seat cannot be purchased for the chosen segment.

  Occupied seats are not shown to the client directly; if a seat is taken on at
  least one of the relevant segments it appears as `blocked`.

- **Admin mode** exposes a third status:
  - `occupied` &mdash; the seat is already sold and is displayed in red.

  In this mode an administrator can block or unblock seats and also reassign
  passengers between occupied seats.

## Bus Layout Variants

The application supports two bus layout variants:

1. **Neoplan** &ndash; variant `1` with 46 seats.
2. **Travego** &ndash; variant `2` with 48 seats.

When creating or editing a tour the backend expects the `layout_variant` field in
the payload so that it can generate the proper number of seats. The front end
reads the same field and automatically renders the corresponding layout.
Set `REACT_APP_API_URL` in `frontend/.env` to point the React app to your
backend instance; no additional environment variables are required for selecting
the layout variant.

## Horizontal layout with icons

The bus layouts include a compact horizontal view. Driver position, wheels and
doors are represented with small SVG icons so the orientation of the bus remains
clear even on wide screens. The seat numbers are arranged from left to right in
rows to match the real arrangement inside the coach.

## External frontend: payment flow via cookie session + CSRF

For browser-based integrations with public purchase endpoints, follow this order
strictly:

1. Get `deep_link` / `opaque` from the ticket link payload.
2. Open `GET /q/{opaque}` in the browser to initialize:
   - purchase session cookie (`minicab_purchase_{purchase_id}`),
   - CSRF cookie (`mc_csrf`).
3. Call `POST /public/purchase/{purchase_id}/pay` with:
   - browser cookies from step 2,
   - `X-CSRF` header with the token from `mc_csrf` cookie,
   - `credentials: 'include'` (or `withCredentials: true` for axios).

If step 2 is skipped, `POST /public/...` requests will fail because the backend
will not see a valid purchase session and CSRF context.

### Browser checklist (API gateway / client)

- Ensure cookie forwarding is enabled end-to-end (`credentials: 'include'` / `withCredentials: true`).
- Ensure the gateway does not strip `Set-Cookie` from `GET /q/{opaque}`.
- Ensure cookie attributes are compatible with your deployment:
  - `SameSite=None; Secure` for cross-site frontend/backend.
  - shared/parent `Domain` when frontend and API are on subdomains.
- Ensure `X-CSRF` header is forwarded by the gateway to backend.

### Browser example (`fetch`, with credentials)

```js
// 1) Initialize cookie session by opening the deep link once in browser context
await fetch(`${API_BASE}/q/${opaque}`, {
  method: 'GET',
  credentials: 'include',
  redirect: 'follow'
});

// 2) Read CSRF token from cookie and send payment request
const csrf = document.cookie
  .split('; ')
  .find((row) => row.startsWith('mc_csrf='))
  ?.split('=')[1];

const payRes = await fetch(`${API_BASE}/public/purchase/${purchaseId}/pay`, {
  method: 'POST',
  credentials: 'include',
  headers: {
    'X-CSRF': decodeURIComponent(csrf || '')
  }
});

const payPayload = await payRes.json();
console.log(payPayload);
```

Example successful response:

```json
{
  "provider": "liqpay",
  "data": "eyJ2ZXJzaW9uIjozLCJwdWJsaWNfa2V5Ijoi...",
  "signature": "Q1Q4QXh3b3...",
  "payload": {
    "version": 3,
    "action": "pay",
    "amount": "250.00",
    "currency": "UAH",
    "description": "Purchase #555",
    "order_id": "purchase-555-1700000000"
  }
}
```

### Browser example (`axios`, `withCredentials`)

```js
await axios.get(`${API_BASE}/q/${opaque}`, { withCredentials: true });

const csrf = Cookies.get('mc_csrf');

const { data } = await axios.post(
  `${API_BASE}/public/purchase/${purchaseId}/pay`,
  null,
  {
    withCredentials: true,
    headers: { 'X-CSRF': csrf }
  }
);
```

## Learn More

You can learn more in the [Create React App documentation](https://facebook.github.io/create-react-app/docs/getting-started).

To learn React, check out the [React documentation](https://reactjs.org/).

### Code Splitting

This section has moved here: [https://facebook.github.io/create-react-app/docs/code-splitting](https://facebook.github.io/create-react-app/docs/code-splitting)

### Analyzing the Bundle Size

This section has moved here: [https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size](https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size)

### Making a Progressive Web App

This section has moved here: [https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app](https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app)

### Advanced Configuration

This section has moved here: [https://facebook.github.io/create-react-app/docs/advanced-configuration](https://facebook.github.io/create-react-app/docs/advanced-configuration)

### Deployment

This section has moved here: [https://facebook.github.io/create-react-app/docs/deployment](https://facebook.github.io/create-react-app/docs/deployment)

### `npm run build` fails to minify

This section has moved here: [https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify](https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify)
