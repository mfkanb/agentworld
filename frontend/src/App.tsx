import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import WorldPage from './pages/world/WorldPage';
import XiapingPage from './pages/xiaping/XiapingPage';
import BarPage from './pages/bar/BarPage';
import FriendsPage from './pages/friends/FriendsPage';
import InstreetPage from './pages/instreet/InstreetPage';
import NeverlandPage from './pages/neverland/NeverlandPage';
import TravelPage from './pages/travel/TravelPage';
import PlaylabPage from './pages/playlab/PlaylabPage';
import CheckinPage from './pages/common/CommonPages';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<WorldPage />} />
          <Route path="/xiaping" element={<XiapingPage />} />
          <Route path="/bar" element={<BarPage />} />
          <Route path="/friends" element={<FriendsPage />} />
          <Route path="/instreet" element={<InstreetPage />} />
          <Route path="/neverland" element={<NeverlandPage />} />
          <Route path="/travel" element={<TravelPage />} />
          <Route path="/playlab" element={<PlaylabPage />} />
          <Route path="/checkin" element={<CheckinPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
