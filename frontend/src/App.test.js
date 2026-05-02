import { render, screen } from '@testing-library/react';
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
import App from './App';

test('renders login', () => {
  render(<App />);
  const heading = screen.getByRole('heading', { name: /Login/i });
  expect(heading).toBeInTheDocument();
});
