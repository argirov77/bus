import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
import App from './App';

test('renders login', () => {
  render(<App />);
  const heading = screen.getByRole('heading', { name: /Login/i });
  expect(heading).toBeInTheDocument();
});

test('checkbox health loading and success render', async () => {
  localStorage.setItem('token', 't');
  axios.get.mockImplementation((url) => {
    if (url === '/auth/verify') return Promise.resolve({ data: {} });
    if (url === '/admin/integrations/checkbox/health') return Promise.resolve({ data: { status: 'ok', message: 'ok', details: [] } });
    return Promise.resolve({ data: {} });
  });

  render(<App />);
  const btn = await screen.findByRole('button', { name: /Проверить CheckBox/i });
  fireEvent.click(btn);
  expect(screen.getByRole('button', { name: /Проверка.../i })).toBeDisabled();
  await waitFor(() => expect(screen.getByText(/Статус: ok/i)).toBeInTheDocument());
});

test('checkbox health error render', async () => {
  localStorage.setItem('token', 't');
  axios.get.mockImplementation((url) => {
    if (url === '/auth/verify') return Promise.resolve({ data: {} });
    if (url === '/admin/integrations/checkbox/health') return Promise.reject({ response: { data: { status: 'error', message: 'network', details: ['network'] } } });
    return Promise.resolve({ data: {} });
  });

  render(<App />);
  const btn = await screen.findByRole('button', { name: /Проверить CheckBox/i });
  fireEvent.click(btn);
  await waitFor(() => expect(screen.getByText(/Статус: error/i)).toBeInTheDocument());
});
