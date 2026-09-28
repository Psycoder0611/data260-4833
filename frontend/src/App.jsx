import { Routes, Route, Link } from "react-router-dom";

import Home from "./pages/Home";
import Login from "./pages/Login";
import CreateRecord from "./pages/CreateRecord";
import UpdateRecord from "./pages/UpdateRecord";
import DeleteRecord from "./pages/DeleteRecord";

function App() {
  const apiBaseUrl = "http://localhost:8333";

  return (
    <div>
      <nav>
        <Link to="/">Home</Link>
        {" | "}
        <Link to="/login">Login</Link>
        {" | "}
        <Link to="/create">Add Record</Link>
        {" | "}
        <Link to="/update">Update Record</Link>
        {" | "}
        <Link to="/delete">Delete Record</Link>
      </nav>

      <Routes>
        <Route
          path="/"
          element={<Home />}
        />

        <Route
          path="/login"
          element={<Login />}
        />

        <Route
          path="/create"
          element={<CreateRecord apiBaseUrl={apiBaseUrl} />}
        />

        <Route
          path="/update"
          element={<UpdateRecord apiBaseUrl={apiBaseUrl} />}
        />

        <Route
          path="/delete"
          element={<DeleteRecord apiBaseUrl={apiBaseUrl} />}
        />
      </Routes>
    </div>
  );
}

export default App;