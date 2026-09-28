import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

function DeleteRecord({ apiBaseUrl }) {
  const [id, setId] = useState("");
  const [error, setError] = useState("");

  const navigate = useNavigate();

  const handleDelete = async (event) => {
    event.preventDefault();
    setError("");

    try {
      await axios.delete(
        `${apiBaseUrl}/api/hw4/trials/${id}`,
        {
          withCredentials: true,
        }
      );

      navigate("/");
    } catch (err) {
      if (err.response?.status === 401) {
        setError("Login required");
      } else if (err.response?.status === 404) {
        setError("Clinical trial not found");
      } else {
        setError("Unable to delete clinical trial");
      }
    }
  };

  return (
    <div className="page-container">
      <h1>Delete Clinical Trial</h1>

      <form onSubmit={handleDelete}>
        <div>
          <label htmlFor="id">Trial ID</label>
          <br />

          <input
            id="id"
            type="number"
            value={id}
            onChange={(event) => setId(event.target.value)}
            placeholder="Enter trial ID"
            required
          />
        </div>

        <button type="submit">
          Delete Clinical Trial
        </button>
      </form>

      {error && <p>{error}</p>}
    </div>
  );
}

export default DeleteRecord;