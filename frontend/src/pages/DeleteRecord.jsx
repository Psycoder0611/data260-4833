import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";

import { deleteTrial } from "../features/trials/trialsSlice";


function DeleteRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const { loading, error } = useSelector(
    (state) => state.trials
  );

  const [id, setId] = useState("");


  const handleDelete = async (event) => {
    event.preventDefault();

    try {
      await dispatch(
        deleteTrial(Number(id))
      ).unwrap();

      navigate("/");
    } catch {
      // Redux stores the API error in state.
    }
  };


  return (
    <div className="page-container">
      <h1>Delete Clinical Trial</h1>

      <form onSubmit={handleDelete}>

        <div>
          <label htmlFor="id">
            Trial ID
          </label>

          <input
            id="id"
            type="number"
            min="1"
            value={id}
            onChange={(event) =>
              setId(event.target.value)
            }
            placeholder="Enter trial ID"
            required
          />
        </div>


        <button type="submit" disabled={loading}>
          {loading ? "Deleting..." : "Delete Clinical Trial"}
        </button>

      </form>

      {error && (
        <p className="error-message">
          {error}
        </p>
      )}
    </div>
  );
}


export default DeleteRecord;